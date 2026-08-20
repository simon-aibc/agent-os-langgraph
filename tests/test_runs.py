import contextlib
import sqlite3
from pathlib import Path

import pytest

from agent_os.checkpoints import CHECKPOINT_DB_ENV
from agent_os.runs import (
    _get_db_path,
    _init_runs_db,
    append_event,
    create_run,
    get_run,
    list_events,
    list_runs,
    set_status,
)


@pytest.fixture
def runs_db(tmp_path, monkeypatch):
    monkeypatch.setenv(CHECKPOINT_DB_ENV, str(tmp_path / "checkpoints.db"))
    # The ledger lives in its own derived file, not the checkpoint DB.
    return Path(_get_db_path())


def test_init_runs_db_creates_tables(runs_db):
    _init_runs_db()

    with contextlib.closing(sqlite3.connect(runs_db)) as conn:
        cursor = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name IN ('runs', 'run_events')
            ORDER BY name
            """
        )
        assert [row[0] for row in cursor.fetchall()] == ["run_events", "runs"]


def test_run_events_use_monotonic_seq_under_interleaved_appends(runs_db):
    first_run = create_run("thread-1", "workspace-a", "first task")
    second_run = create_run("thread-2", "workspace-a", "second task")

    assert append_event(first_run, "status", {"status": "running"}) == 1
    assert append_event(second_run, "status", {"status": "running"}) == 1
    assert append_event(first_run, "node", {"name": "architect"}) == 2
    assert append_event(second_run, "result", {"ok": True}) == 2
    assert append_event(first_run, "interrupt", {"reason": "approval"}) == 3

    first_events = list_events(first_run)
    second_events = list_events(second_run)

    assert [event["seq"] for event in first_events] == [1, 2, 3]
    assert [event["seq"] for event in second_events] == [1, 2]
    assert [event["seq"] for event in list_events(first_run, after=1)] == [2, 3]
    assert first_events[1]["payload"] == {"name": "architect"}


def test_set_status_updates_transitions_and_terminal_fields(runs_db):
    run_id = create_run("thread-1", None, "task")

    set_status(run_id, "running")
    running = get_run(run_id)
    assert running is not None
    assert running["status"] == "running"
    assert running["ended_at"] is None
    assert running["error"] is None

    set_status(run_id, "interrupted")
    interrupted = get_run(run_id)
    assert interrupted is not None
    assert interrupted["status"] == "interrupted"
    assert interrupted["ended_at"] is None

    set_status(run_id, "error", error="boom", ended=True)
    failed = get_run(run_id)
    assert failed is not None
    assert failed["status"] == "error"
    assert failed["error"] == "boom"
    assert failed["ended_at"] is not None


def test_list_runs_supports_status_workspace_and_limit_filters(runs_db):
    first = create_run("thread-1", "workspace-a", "first")
    second = create_run("thread-2", "workspace-b", "second")
    third = create_run("thread-3", "workspace-a", "third")
    set_status(second, "running")
    set_status(third, "running")

    assert [run["run_id"] for run in list_runs(status="queued")] == [first]
    assert {run["run_id"] for run in list_runs(workspace="workspace-a")} == {
        first,
        third,
    }
    assert [
        run["run_id"] for run in list_runs(status="running", workspace="workspace-a")
    ] == [third]
    assert len(list_runs(limit=2)) == 2
