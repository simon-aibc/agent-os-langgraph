import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rich.console import Console

from agent_os.cli.app import async_main
from agent_os.observations import (
    MAX_ADVISORIES,
    ObservationValidationError,
    SqliteObservationStore,
    observation_workspace_id,
    open_observation_store,
    render_advisory_context,
)
from agent_os.server.api import EXECUTION_TOKEN_ENV, app


def _store(path: Path) -> SqliteObservationStore:
    return SqliteObservationStore(str(path))


def _record(store: SqliteObservationStore, workspace: str, *, kind: str = "memory_write"):
    return store.create(
        workspace_id=workspace,
        run_id="run-1",
        thread_id="thread-1",
        task_kind=kind,
        approach="native_tool:memory_write",
        outcome_signal="unknown",
        outcome_evidence="terminal_status=completed",
        source="server.run",
    )


def test_observations_persist_and_require_explicit_outcomes(tmp_path: Path) -> None:
    path = tmp_path / "observations.db"
    store = _store(path)
    observation = _record(store, "workspace-a")

    reloaded = _store(path).get(observation.observation_id)
    assert reloaded is not None
    assert reloaded.schema_version == 1
    assert reloaded.outcome_signal == "unknown"
    assert reloaded.outcome_evidence == "terminal_status=completed"

    updated = store.record_outcome(
        observation.observation_id,
        signal="edited",
        evidence="Operator adjusted the delivered artifact.",
    )
    assert updated is not None
    assert updated.outcome_signal == "edited"
    assert updated.outcome_evidence == "Operator adjusted the delivered artifact."


def test_observation_validation_and_workspace_isolation(tmp_path: Path) -> None:
    store = _store(tmp_path / "observations.db")
    first = _record(store, "workspace-a")
    _record(store, "workspace-b")

    assert [item.observation_id for item in store.list(workspace_id="workspace-a")] == [
        first.observation_id
    ]
    try:
        store.record_outcome(first.observation_id, signal="unknown", evidence=None)
    except ObservationValidationError as exc:
        assert "accepted, rejected, or edited" in str(exc)
    else:
        raise AssertionError("unknown must not be an operator-recorded outcome")


def test_observation_store_open_is_fail_safe(monkeypatch) -> None:
    def broken_store(path: str):
        raise OSError(f"cannot open {path}")

    monkeypatch.setattr("agent_os.observations.SqliteObservationStore", broken_store)

    assert open_observation_store() is None


def test_advisory_retrieval_is_bounded_relevant_and_not_unknown(tmp_path: Path) -> None:
    store = _store(tmp_path / "observations.db")
    for index in range(MAX_ADVISORIES + 2):
        record = _record(store, "workspace-a")
        store.record_outcome(record.observation_id, signal="accepted", evidence=f"review {index}")
    unknown = _record(store, "workspace-a")
    other_kind = _record(store, "workspace-a", kind="workflow")
    store.record_outcome(other_kind.observation_id, signal="rejected", evidence="not relevant")

    context = render_advisory_context(
        store,
        workspace_id="workspace-a",
        task_kind="memory_write",
    )
    assert context.count("Historical evidence only") == MAX_ADVISORIES
    assert "advisory only" in context
    assert unknown.observation_id not in context
    assert "not relevant" not in context


def test_runtime_initial_state_injects_fixed_strategy_not_raw_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agent_os.server import runtime

    database = tmp_path / "observations.db"
    monkeypatch.setenv("AGENT_OS_OBSERVATIONS_DB", str(database))
    monkeypatch.setattr(runtime, "composed_workspace", lambda: None)
    store = _store(database)
    record = _record(store, "standalone")
    store.record_outcome(record.observation_id, signal="edited", evidence="Operator refined it")

    state = runtime.initial_state("private task text", run_id="run-strategy")

    assert state["observation_context"] is None
    hint = state["strategy_hint"]
    assert hint is not None
    assert "Operator refined it" not in hint.directive
    assert "private task text" not in hint.directive


@pytest.mark.anyio
async def test_observations_cli_lists_and_records_workspace_outcome(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workspace_path = workspace / "workspace.toml"
    workspace_path.write_text('[workspace]\nname = "observations"\n', encoding="utf-8")
    monkeypatch.delenv("AGENT_OS_OBSERVATIONS_DB", raising=False)
    store = _store(workspace / "observations.db")
    record = _record(store, observation_workspace_id(workspace))
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)

    listed = await async_main(
        ["observations", "list", "--workspace", str(workspace_path)], console=console
    )
    recorded = await async_main(
        [
            "observations",
            "record-outcome",
            record.observation_id,
            "--signal",
            "accepted",
            "--evidence",
            "Reviewed by operator",
            "--workspace",
            str(workspace_path),
        ],
        console=console,
    )
    assert listed == 0
    assert recorded == 0
    assert store.get(record.observation_id).outcome_signal == "accepted"
    assert record.observation_id in output.getvalue()


def test_observations_api_uses_private_auth_and_updates_outcome(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "observations.db"
    monkeypatch.setenv("AGENT_OS_OBSERVATIONS_DB", str(database))
    monkeypatch.setenv(EXECUTION_TOKEN_ENV, "observation-token")
    store = _store(database)
    record = _record(store, "standalone")
    client = TestClient(app)

    assert client.get("/api/observations").status_code == 403
    headers = {"X-Execution-Token": "observation-token"}
    listed = client.get("/api/observations", headers=headers)
    assert listed.status_code == 200
    assert [item["observation_id"] for item in listed.json()] == [record.observation_id]

    updated = client.post(
        f"/api/observations/{record.observation_id}/outcome",
        headers=headers,
        json={"signal": "rejected", "evidence": "Operator rejected result"},
    )
    assert updated.status_code == 200
    assert updated.json()["outcome_signal"] == "rejected"
