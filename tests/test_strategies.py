from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_os.observations import SqliteObservationStore
from agent_os.strategies import select_strategy


def _labelled(
    store: SqliteObservationStore,
    *,
    workspace: str,
    strategy: str,
    signal: str,
    count: int = 1,
) -> None:
    for index in range(count):
        observation = store.create(
            workspace_id=workspace,
            run_id=f"{workspace}-{strategy}-{index}",
            thread_id="thread",
            task_kind="workflow",
            approach=strategy,
            outcome_signal="unknown",
            outcome_evidence="terminal_status=completed",
            source="server.run",
        )
        store.record_outcome(observation.observation_id, signal=signal, evidence="operator label")


def test_aggregation_excludes_unknown_and_evidence_backed_selection_is_isolated(
    tmp_path: Path,
) -> None:
    store = SqliteObservationStore(str(tmp_path / "observations.db"))
    _labelled(store, workspace="alpha", strategy="default-v1", signal="accepted", count=5)
    _labelled(
        store,
        workspace="alpha",
        strategy="verification-first-v1",
        signal="rejected",
        count=5,
    )
    unknown = store.create(
        workspace_id="alpha",
        run_id="unknown",
        thread_id="thread",
        task_kind="workflow",
        approach="default-v1",
        outcome_signal="unknown",
        outcome_evidence="terminal_status=completed",
        source="server.run",
    )

    selected = select_strategy(store, workspace_id="alpha", task_kind="workflow", run_id="next")
    assert selected.hint.strategy_id == "default-v1"
    assert selected.hint.selection_reason == "evidence_backed"
    default_pattern = next(item for item in selected.patterns if item.strategy_id == "default-v1")
    assert default_pattern.labelled_count == 5
    assert default_pattern.unknown_count == 1
    assert default_pattern.outcome_score == 1.0

    other_workspace = select_strategy(
        store, workspace_id="beta", task_kind="workflow", run_id="first-beta"
    )
    assert other_workspace.hint.selection_reason == "exploration"
    assert store.get(unknown.observation_id).outcome_signal == "unknown"


def test_exploration_balances_atomically_and_repeat_run_is_stable(tmp_path: Path) -> None:
    database = str(tmp_path / "observations.db")
    SqliteObservationStore(database)

    def choose(index: int) -> str:
        store = SqliteObservationStore(database)
        return select_strategy(
            store,
            workspace_id="workspace",
            task_kind="workflow",
            run_id=f"run-{index}",
        ).hint.strategy_id

    with ThreadPoolExecutor(max_workers=6) as pool:
        selected = list(pool.map(choose, range(12)))
    counts = {strategy: selected.count(strategy) for strategy in set(selected)}
    assert max(counts.values()) - min(counts.values()) <= 1

    store = SqliteObservationStore(database)
    first = select_strategy(store, workspace_id="workspace", task_kind="workflow", run_id="run-0")
    assert first.hint.strategy_id == selected[0]


def test_explicit_override_and_safe_fallbacks(tmp_path: Path) -> None:
    store = SqliteObservationStore(str(tmp_path / "observations.db"))
    explicit = select_strategy(
        store,
        workspace_id="workspace",
        task_kind="workflow",
        run_id="explicit-run",
        explicit_strategy_id="concise-plan-v1",
    )
    assert explicit.hint.strategy_id == "concise-plan-v1"
    assert explicit.hint.selection_reason == "explicit"
    repeated = select_strategy(
        store,
        workspace_id="workspace",
        task_kind="workflow",
        run_id="explicit-run",
    )
    assert repeated.hint.strategy_id == "concise-plan-v1"

    with pytest.raises(ValueError, match="not allowed"):
        select_strategy(
            store,
            workspace_id="workspace",
            task_kind="workflow",
            run_id="bad",
            explicit_strategy_id="untrusted-v1",
        )
    assert select_strategy(None, workspace_id="workspace", task_kind="workflow", run_id="none").hint.strategy_id == "default-v1"
    assert select_strategy(store, workspace_id="workspace", task_kind="memory_write", run_id="tool").hint.selection_reason == "default"
