from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.types import Command

from agent_os.checkpoints import CHECKPOINT_DB_ENV
from agent_os.runs import create_run, get_run, list_events
from agent_os.server.run_executor import execute_run


class FakeGraph:
    def __init__(
        self,
        events: list[dict[str, Any]],
        snapshot: object,
        *,
        stream_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.snapshot = snapshot
        self.stream_error = stream_error
        self.seen_input: object | None = None
        self.seen_config: dict[str, Any] | None = None
        self.seen_version: str | None = None

    async def astream_events(
        self,
        graph_input: object,
        config: dict[str, Any],
        version: str,
    ):
        self.seen_input = graph_input
        self.seen_config = config
        self.seen_version = version
        if self.stream_error is not None:
            raise self.stream_error
        for event in self.events:
            yield event

    async def aget_state(self, config: dict[str, Any]) -> object:
        self.seen_config = config
        return self.snapshot


@pytest.fixture
def runs_db(tmp_path, monkeypatch):
    database_path = tmp_path / "checkpoints.db"
    monkeypatch.setenv(CHECKPOINT_DB_ENV, str(database_path))
    monkeypatch.setenv("AGENT_OS_SANDBOX", str(tmp_path))
    return database_path


def _completed_snapshot() -> object:
    return SimpleNamespace(tasks=())


def _interrupted_snapshot(prompt: object = "Approve?") -> object:
    interrupt = SimpleNamespace(value=prompt)
    task = SimpleNamespace(interrupts=(interrupt,))
    return SimpleNamespace(tasks=(task,))


def _patch_graph(monkeypatch, graph: FakeGraph) -> None:
    def build_graph(checkpointer=None):
        return graph

    monkeypatch.setattr("agent_os.graph.build_graph", build_graph)


@pytest.mark.anyio
async def test_execute_run_translates_node_token_and_result_events(runs_db, monkeypatch):
    graph = FakeGraph(
        [
            {"event": "on_chain_start", "name": "planner"},
            {
                "event": "on_chat_model_stream",
                "data": {"chunk": SimpleNamespace(content="Hel")},
            },
            {
                "event": "on_chat_model_stream",
                "data": {"chunk": SimpleNamespace(content="lo")},
            },
            {"event": "on_chain_end", "name": "planner"},
        ],
        _completed_snapshot(),
    )
    _patch_graph(monkeypatch, graph)
    workspace = runs_db.parent / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AGENT_OS_SANDBOX", str(runs_db.parent))
    run_id = create_run("thread-1", str(workspace), "task")

    await execute_run(run_id, "thread-1", "task")

    assert graph.seen_config == {
        "recursion_limit": 7,
        "configurable": {"thread_id": "thread-1"},
    }
    assert graph.seen_version == "v1"
    assert get_run(run_id)["status"] == "completed"
    events = list_events(run_id)
    assert [event["kind"] for event in events] == [
        "node",
        "token",
        "token",
        "node",
        "result",
    ]
    assert events[0]["payload"] == {"name": "planner", "event": "on_chain_start"}
    assert events[1]["payload"] == {"content": "Hel"}


@pytest.mark.anyio
async def test_execute_run_binds_the_persisted_workspace(runs_db, monkeypatch):
    from agent_os.sandbox import get_sandbox_root

    workspace = runs_db.parent / "project"
    workspace.mkdir()
    monkeypatch.setenv("AGENT_OS_SANDBOX", str(runs_db.parent))

    class WorkspaceGraph(FakeGraph):
        async def astream_events(self, graph_input, config, version):
            assert get_sandbox_root() == workspace.resolve()
            if False:
                yield {}

    graph = WorkspaceGraph([], _completed_snapshot())
    _patch_graph(monkeypatch, graph)
    run_id = create_run("thread-workspace", str(workspace), "task")

    await execute_run(run_id, "thread-workspace", "task")

    assert get_run(run_id)["status"] == "completed"


@pytest.mark.anyio
async def test_execute_run_records_interrupt_and_resume_command(runs_db, monkeypatch):
    graph = FakeGraph([], _interrupted_snapshot("Review plan"))
    _patch_graph(monkeypatch, graph)
    run_id = create_run("thread-2", None, "task")

    await execute_run(run_id, "thread-2", "task", resume_feedback="approved")

    assert isinstance(graph.seen_input, Command)
    assert get_run(run_id)["status"] == "interrupted"
    events = list_events(run_id)
    assert [event["kind"] for event in events] == ["interrupt"]
    assert events[0]["payload"] == {"prompt": "Review plan"}


@pytest.mark.anyio
async def test_execute_run_records_error_path(runs_db, monkeypatch):
    graph = FakeGraph([], _completed_snapshot(), stream_error=RuntimeError("boom"))
    _patch_graph(monkeypatch, graph)
    run_id = create_run("thread-3", None, "task")

    await execute_run(run_id, "thread-3", "task")

    run = get_run(run_id)
    assert run["status"] == "error"
    assert run["error"] == "boom"
    assert run["ended_at"] is not None
    events = list_events(run_id)
    assert [event["kind"] for event in events] == ["error"]
    assert events[0]["payload"] == {"message": "boom"}
