from typing import cast

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent_os.graph import build_graph
from agent_os.routing import build_runtime_config
from agent_os.schemas import ArchitectBrief, ExecutorReport
from agent_os.state import SimonState


def make_state(**overrides: object) -> SimonState:
    state: dict[str, object] = {
        "messages": [],
        "task": "do something normal",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "human_feedback": None,
        "hot_context": None,
    }
    state.update(overrides)
    return cast(SimonState, state)


class ArchitectSpy:
    def __init__(self) -> None:
        self.feedback: list[str | None] = []

    def __call__(self, state: SimonState) -> dict[str, ArchitectBrief]:
        feedback = state.get("human_feedback")
        self.feedback.append(feedback)
        change = "implement requested change"
        if feedback and feedback.startswith("rejected:"):
            change = f"revise plan using feedback: {feedback}"
        return {
            "plan": ArchitectBrief(
                files=["dummy.py"],
                changes=[change],
                verify_cmd="pytest",
            )
        }


class ExecutorSpy:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, state: SimonState) -> dict[str, ExecutorReport]:
        self.call_count += 1
        return {
            "executor_output": ExecutorReport(
                diff="updated dummy.py",
                verify_output="tests passed",
                success=True,
            )
        }


def build_test_graph():
    architect = ArchitectSpy()
    executor = ExecutorSpy()
    checkpointer = InMemorySaver()
    graph = build_graph(
        architect_node_impl=architect,
        executor_node_impl=executor,
        checkpointer=checkpointer,
    )
    return graph, architect, executor, checkpointer


def test_build_graph_compiles_with_default_and_injected_checkpointers():
    default_graph = build_graph(
        architect_node_impl=ArchitectSpy(),
        executor_node_impl=ExecutorSpy(),
    )
    assert isinstance(default_graph.checkpointer, InMemorySaver)

    graph, _, _, checkpointer = build_test_graph()
    assert graph.checkpointer is checkpointer
    assert set(graph.nodes) == {
        "__start__",
        "planner",
        "supervisor",
        "architect",
        "human_gate",
        "executor",
        "tool_dispatcher",
    }


def test_default_checkpointer_requires_thread_id():
    graph = build_graph(
        architect_node_impl=ArchitectSpy(),
        executor_node_impl=ExecutorSpy(),
    )

    with pytest.raises(ValueError, match="thread_id"):
        graph.invoke(make_state())


def test_graph_pauses_at_human_gate_before_executor():
    graph, architect, executor, _ = build_test_graph()
    config = build_runtime_config("pause-flow")

    result = graph.invoke(make_state(), config=config)

    assert architect.feedback == [None]
    assert executor.call_count == 0
    assert "__interrupt__" in result
    prompt = result["__interrupt__"][0].value
    assert "ArchitectBrief JSON" in prompt
    assert '"dummy.py"' in prompt
    assert '"verify_cmd": "pytest"' in prompt

    snapshot = graph.get_state(config)
    assert snapshot.next == ("human_gate",)
    assert snapshot.tasks[0].interrupts[0].value == prompt


def test_graph_approve_resume_executes_once_and_terminates():
    graph, architect, executor, _ = build_test_graph()
    config = build_runtime_config("approve-flow")

    paused = graph.invoke(make_state(), config=config)
    assert "__interrupt__" in paused
    assert architect.feedback == [None]
    assert executor.call_count == 0

    result = graph.invoke(Command(resume="approved"), config=config)

    assert result["human_feedback"] == "approved"
    assert isinstance(result["executor_output"], ExecutorReport)
    assert result["executor_output"].success is True
    assert executor.call_count == 1
    assert graph.get_state(config).next == ()

    repeated = graph.invoke(Command(resume="approved"), config=config)
    assert repeated == result
    assert executor.call_count == 1


def test_graph_rejection_returns_feedback_to_architect_and_pauses_again():
    graph, architect, executor, _ = build_test_graph()
    config = build_runtime_config("reject-flow")

    graph.invoke(make_state(), config=config)
    assert architect.feedback == [None]
    assert executor.call_count == 0

    feedback = "rejected: add rollback tests"
    result = graph.invoke(Command(resume=feedback), config=config)

    assert "__interrupt__" in result
    assert architect.feedback == [None, feedback]
    assert executor.call_count == 0
    assert "revise plan using feedback" in result["plan"].changes[0]

    snapshot = graph.get_state(config)
    assert snapshot.next == ("human_gate",)
    assert snapshot.values["human_feedback"] == feedback
    assert snapshot.values["executor_output"] is None


def test_graph_accepts_approval_alias():
    graph, _, executor, _ = build_test_graph()
    config = build_runtime_config("approval-alias")

    graph.invoke(make_state(), config=config)
    result = graph.invoke(Command(resume="y"), config=config)

    assert result["human_feedback"] == "approved"
    assert executor.call_count == 1


def test_graph_thread_checkpoints_are_isolated():
    graph, _, _, _ = build_test_graph()
    first_config = build_runtime_config("thread-one")
    second_config = build_runtime_config("thread-two")

    graph.invoke(make_state(task="first task"), config=first_config)

    assert graph.get_state(first_config).next == ("human_gate",)
    assert graph.get_state(second_config).next == ()
    assert graph.get_state(second_config).values == {}


def test_graph_skill_task_routes_to_tool_dispatcher():
    graph, _, executor, _ = build_test_graph()
    config = build_runtime_config("skill-route")

    visited = [
        next(iter(step))
        for step in graph.stream(
            make_state(task="please research the repository"),
            config=config,
        )
    ]

    assert visited == ["planner", "supervisor", "tool_dispatcher"]
    assert executor.call_count == 0


def test_graph_legacy_approval_routes_directly_to_executor():
    graph, architect, executor, _ = build_test_graph()
    config = build_runtime_config("legacy-approval")
    plan = ArchitectBrief(files=[], changes=[], verify_cmd="pytest")

    visited = [
        next(iter(step))
        for step in graph.stream(
            make_state(plan=plan, approval=True),
            config=config,
        )
    ]

    assert visited == ["planner", "supervisor", "executor", "supervisor"]
    assert architect.feedback == []
    assert executor.call_count == 1


def test_graph_completed_output_terminates_without_executor():
    graph, architect, executor, _ = build_test_graph()
    config = build_runtime_config("completed-output")
    report = ExecutorReport(diff="done", verify_output="passed", success=True)

    visited = [
        next(iter(step))
        for step in graph.stream(
            make_state(executor_output=report),
            config=config,
        )
    ]

    assert visited == ["planner", "supervisor"]
    assert architect.feedback == []
    assert executor.call_count == 0
