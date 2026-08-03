import io
import os
from types import SimpleNamespace

import pytest
from rich.console import Console

from agent_os.bindings import resolve_backend_binding
from agent_os.cli.app import async_main
from agent_os.schemas import ToolExecutionResult


def make_console() -> tuple[Console, io.StringIO]:
    output = io.StringIO()
    return (
        Console(
            file=output,
            force_terminal=False,
            color_system=None,
            width=120,
        ),
        output,
    )


def completed_snapshot():
    return SimpleNamespace(created_at="now", values={"task": "done"}, next=(), tasks=())


class CompletedGraph:
    def __init__(self):
        self.calls = []

    async def astream_events(self, state, config, version):
        self.calls.append((state, config, version))
        yield {"event": "unknown"}

    async def aget_state(self, config):
        return completed_snapshot()


class ToolFailureCompletedGraph(CompletedGraph):
    async def aget_state(self, config):
        return SimpleNamespace(
            created_at="now",
            values={
                "tool_result": ToolExecutionResult(
                    tool="bash",
                    output="returncode=-1",
                    success=False,
                )
            },
            next=(),
            tasks=(),
        )


@pytest.mark.anyio
async def test_new_workflow_passes_state_config_and_v2_events():
    graph = CompletedGraph()
    console, output = make_console()

    code = await async_main(
        ["test task", "--thread-id", "thread-1"],
        graph_factory=lambda: graph,
        console=console,
    )

    assert code == 0
    state, config, version = graph.calls[0]
    assert state["task"] == "test task"
    assert state["messages"] == [("user", "test task")]
    assert config["configurable"]["thread_id"] == "thread-1"
    assert version == "v2"
    assert "[THREAD] thread-1" in output.getvalue()


@pytest.mark.anyio
async def test_completed_tool_failure_returns_nonzero_exit():
    console, output = make_console()

    code = await async_main(
        ["bash python", "--thread-id", "tool-failure"],
        graph_factory=ToolFailureCompletedGraph,
        console=console,
    )

    assert code == 1
    assert "[THREAD] tool-failure" in output.getvalue()


@pytest.mark.anyio
async def test_generated_thread_id_and_sandbox_precede_graph_factory(
    tmp_path,
    monkeypatch,
):
    console, output = make_console()
    sandbox = tmp_path / "sandbox"
    monkeypatch.delenv("AGENT_OS_SANDBOX", raising=False)

    def graph_factory():
        assert os.environ["AGENT_OS_SANDBOX"] == str(sandbox)
        return CompletedGraph()

    code = await async_main(
        ["task", "--sandbox", str(sandbox)],
        graph_factory=graph_factory,
        console=console,
    )

    assert code == 0
    assert "[THREAD] " in output.getvalue()
    assert "AGENT_OS_SANDBOX" not in os.environ


@pytest.mark.anyio
@pytest.mark.parametrize(
    "argv,error",
    [
        ([], "Task is required"),
        (["--resume"], "--thread-id is required"),
        (
            ["new task", "--resume", "--thread-id", "existing"],
            "Do not provide a task",
        ),
    ],
)
async def test_cli_argument_contract(argv, error):
    console, output = make_console()

    code = await async_main(argv, graph_factory=CompletedGraph, console=console)

    assert code == 2
    assert error in output.getvalue()


class InterruptGraph:
    def __init__(self, *, start_paused: bool = False):
        self.stage = "paused" if start_paused else "new"
        self.resumes = []

    def snapshot(self):
        if self.stage == "done":
            return completed_snapshot()
        if self.stage == "new":
            return SimpleNamespace(created_at=None, values={}, next=(), tasks=())
        interrupt = SimpleNamespace(value="Approve the implementation plan?")
        task = SimpleNamespace(interrupts=(interrupt,))
        return SimpleNamespace(
            created_at="now",
            values={
                "task": "existing",
                "backend_binding": resolve_backend_binding(None),
            },
            next=("human_gate",),
            tasks=(task,),
        )

    async def aget_state(self, config):
        return self.snapshot()

    async def astream_events(self, state, config, version):
        if self.stage == "new":
            self.stage = "paused"
        else:
            self.resumes.append(state.resume)
            self.stage = "done" if state.resume == "approved" else "paused"
        yield {"event": "unknown"}


@pytest.mark.anyio
async def test_invalid_feedback_reprompts_then_approves():
    graph = InterruptGraph()
    console, output = make_console()
    answers = iter(["maybe", "approved"])

    code = await async_main(
        ["task", "--thread-id", "feedback-test"],
        graph_factory=lambda: graph,
        input_fn=lambda _: next(answers),
        console=console,
    )

    assert code == 0
    assert graph.resumes == ["approved"]
    assert "Invalid feedback" in output.getvalue()
    assert output.getvalue().count("[HUMAN]") == 1


@pytest.mark.anyio
async def test_rejection_returns_to_second_gate_before_approval():
    graph = InterruptGraph()
    console, output = make_console()
    answers = iter(["rejected: add rollback tests", "y"])

    code = await async_main(
        ["task", "--thread-id", "rejection-test"],
        graph_factory=lambda: graph,
        input_fn=lambda _: next(answers),
        console=console,
    )

    assert code == 0
    assert graph.resumes == ["rejected: add rollback tests", "approved"]
    assert output.getvalue().count("[HUMAN]") == 2


@pytest.mark.anyio
async def test_resume_requires_pending_checkpoint():
    console, output = make_console()
    graph = InterruptGraph()

    code = await async_main(
        ["--resume", "--thread-id", "missing"],
        graph_factory=lambda: graph,
        console=console,
    )

    assert code == 2
    assert "Checkpoint not found" in output.getvalue()


@pytest.mark.anyio
async def test_resume_rejects_completed_checkpoint():
    console, output = make_console()

    code = await async_main(
        ["--resume", "--thread-id", "completed"],
        graph_factory=CompletedGraph,
        console=console,
    )

    assert code == 2
    assert "already finished" in output.getvalue()


@pytest.mark.anyio
async def test_resume_mid_run_continues_without_human_interrupt():
    class MidRunGraph(CompletedGraph):
        def __init__(self):
            super().__init__()
            self.stage = "paused"

        async def aget_state(self, config):
            if self.stage == "done":
                return completed_snapshot()
            return SimpleNamespace(
                created_at="now",
                values={
                    "task": "paused mid-model",
                    "backend_binding": resolve_backend_binding(None),
                },
                next=("architect",),
                tasks=(),
            )

        async def astream_events(self, state, config, version):
            self.calls.append((state, config, version))
            self.stage = "done"
            yield {"event": "unknown"}

    graph = MidRunGraph()
    console, output = make_console()
    code = await async_main(
        ["--resume", "--thread-id", "mid-run"],
        graph_factory=lambda: graph,
        console=console,
    )

    assert code == 0
    assert graph.calls[0][0] is None
    assert "Resuming mid-run at node architect" in output.getvalue()


@pytest.mark.anyio
async def test_resume_prompts_before_streaming():
    console, output = make_console()
    graph = InterruptGraph(start_paused=True)

    code = await async_main(
        ["--resume", "--thread-id", "paused"],
        graph_factory=lambda: graph,
        input_fn=lambda _: "approved",
        console=console,
    )

    assert code == 0
    assert graph.resumes == ["approved"]
    assert "[THREAD] paused" in output.getvalue()
    assert "[HUMAN] Approve the implementation plan?" in output.getvalue()


@pytest.mark.anyio
async def test_llm_configuration_error_is_actionable():
    class FailingGraph(CompletedGraph):
        async def astream_events(self, state, config, version):
            raise ValueError("No architect model configured")
            yield

    console, output = make_console()
    code = await async_main(
        ["task"],
        graph_factory=FailingGraph,
        console=console,
    )

    assert code == 1
    assert "Missing or invalid LLM configuration" in output.getvalue()
    assert "LLM_ROUTER" in output.getvalue()
    assert ".env.example" in output.getvalue()


@pytest.mark.anyio
@pytest.mark.parametrize("verbose", [False, True])
async def test_unexpected_workflow_error_traceback_is_verbose_only(verbose):
    class FailingGraph(CompletedGraph):
        async def astream_events(self, state, config, version):
            raise RuntimeError("executor failed")
            yield

    console, output = make_console()
    argv = ["task", "--verbose"] if verbose else ["task"]
    code = await async_main(
        argv,
        graph_factory=FailingGraph,
        console=console,
    )

    assert code == 1
    assert "Workflow failed: executor failed" in output.getvalue()
    assert ("Traceback" in output.getvalue()) is verbose


@pytest.mark.anyio
async def test_graph_initialization_error_is_configuration_failure():
    console, output = make_console()

    def broken_factory():
        raise RuntimeError("cannot open checkpoint")

    code = await async_main(
        ["task"],
        graph_factory=broken_factory,
        console=console,
    )

    assert code == 2
    assert "Failed to initialize workflow" in output.getvalue()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error,expected_code",
    [(EOFError(), 2), (KeyboardInterrupt(), 130)],
)
async def test_human_input_abort_preserves_checkpoint(error, expected_code):
    graph = InterruptGraph(start_paused=True)
    console, output = make_console()

    def abort(_):
        raise error

    code = await async_main(
        ["--resume", "--thread-id", "paused"],
        graph_factory=lambda: graph,
        input_fn=abort,
        console=console,
    )

    assert code == expected_code
    assert "Checkpoint preserved" in output.getvalue()
    assert "agent-os --resume --thread-id paused" in output.getvalue()


@pytest.mark.anyio
async def test_resume_from_preexisting_sqlite_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.types import Command

    from agent_os.checkpoints import get_checkpoint_serializer
    from agent_os.graph import build_graph
    from agent_os.schemas import ArchitectBrief, ExecutorReport

    def architect_node(state):
        return {
            "plan": ArchitectBrief(
                files=["demo.py"],
                changes=["add logging"],
                verify_cmd="pytest",
            )
        }

    def executor_node(state):
        return {
            "executor_output": ExecutorReport(
                diff="updated demo.py",
                verify_output="passed",
                success=True,
            )
        }

    def dispatcher_node(state):
        return Command(
            update={"router_escalated": True},
            goto="supervisor",
        )

    database = tmp_path / "resume.db"
    config = {
        "recursion_limit": 7,
        "configurable": {"thread_id": "sqlite-resume"},
    }
    initial_state = {
        "messages": [],
        "task": "add logging",
        "plan": None,
        "executor_output": None,
        "human_feedback": None,
        "hot_context": None,
        "backend_binding": resolve_backend_binding(None),
    }

    async with AsyncSqliteSaver.from_conn_string(str(database)) as first_saver:
        first_saver.serde = get_checkpoint_serializer()
        first_graph = build_graph(
            architect_node_impl=architect_node,
            executor_node_impl=executor_node,
            tool_dispatcher_node_impl=dispatcher_node,
            checkpointer=first_saver,
        )
        await first_graph.ainvoke(initial_state, config=config)

    async with AsyncSqliteSaver.from_conn_string(str(database)) as second_saver:
        second_saver.serde = get_checkpoint_serializer()
        resumed_graph = build_graph(
            architect_node_impl=architect_node,
            executor_node_impl=executor_node,
            tool_dispatcher_node_impl=dispatcher_node,
            checkpointer=second_saver,
        )
        console, output = make_console()
        code = await async_main(
            ["--resume", "--thread-id", "sqlite-resume"],
            graph_factory=lambda: resumed_graph,
            input_fn=lambda _: "approved",
            console=console,
        )
        snapshot = await resumed_graph.aget_state(config)

    assert code == 0
    assert snapshot.next == ()
    assert snapshot.values["executor_output"].success is True
    assert "[HUMAN]" in output.getvalue()
