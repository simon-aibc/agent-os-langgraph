import pytest

from agent_os.routing import DEFAULT_RUNTIME_CONFIG, build_runtime_config, route_from_state
from agent_os.schemas import ExecutorReport


def test_default_runtime_config_allows_workflow_termination():
    """The runtime config allows six nodes plus the termination superstep."""
    assert DEFAULT_RUNTIME_CONFIG == {"recursion_limit": 7}


def test_build_runtime_config_normalizes_and_requires_thread_id():
    assert build_runtime_config("  workflow-1  ") == {
        "recursion_limit": 7,
        "configurable": {"thread_id": "workflow-1"},
    }
    for invalid_thread_id in ("", " ", "\t\n"):
        with pytest.raises(ValueError, match="thread_id must not be empty"):
            build_runtime_config(invalid_thread_id)


def test_successful_executor_report_routes_to_end():
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": ExecutorReport(diff="done", verify_output="ok", success=True),
        "approval": True,
        "hot_context": None,
    }
    assert route_from_state(state) == "end"


def test_failed_executor_report_with_approval_retries_executor():
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": ExecutorReport(diff="", verify_output="failed", success=False),
        "approval": True,
        "hot_context": None,
    }
    assert route_from_state(state) == "executor"


def test_route_unresolved_task_to_tool():
    """For a new unresolved task -> tool_dispatcher first."""
    state = {
        "messages": [],
        "task": "research the codebase",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "human_feedback": None,
        "hot_context": None,
    }
    assert route_from_state(state) == "tool"


def test_route_escalated_to_architect():
    """When router_escalated is True, supervisor must route to architect."""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "human_feedback": None,
        "hot_context": None,
        "router_escalated": True,
    }
    assert route_from_state(state) == "architect"


def test_route_executor_output():
    """2. if executor_output is present, return 'end'."""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": "Task completed successfully",
        "approval": True,
        "hot_context": None
    }
    assert route_from_state(state) == "end"


def test_route_approval_true():
    """3. if approval is True, return 'executor'."""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": "My plan",
        "executor_output": None,
        "approval": True,
        "hot_context": None
    }
    assert route_from_state(state) == "executor"


def test_route_otherwise_architect():
    """An unresolved task reaches the dispatcher regardless of legacy False."""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "hot_context": None
    }
    # A new unresolved task routes to tool
    assert route_from_state(state) == "tool"

    # Even if approval is False, it goes to tool, which can escalate
    state["approval"] = False
    assert route_from_state(state) == "tool"


def test_route_approved_overrides_approval_false():
    state = {
        "messages": [],
        "task": "do something",
        "plan": None,
        "executor_output": None,
        "approval": False,
        "human_feedback": "approved",
        "hot_context": None,
    }
    assert route_from_state(state) == "executor"


def test_route_rejected_overrides_approval_true():
    state = {
        "messages": [],
        "task": "do something",
        "plan": None,
        "executor_output": None,
        "approval": True,
        "human_feedback": "rejected: bad plan",
        "hot_context": None,
    }
    assert route_from_state(state) == "architect"


def test_route_legacy_approval_works_without_feedback():
    state = {
        "messages": [],
        "task": "do something",
        "plan": None,
        "executor_output": None,
        "approval": True,
        "human_feedback": None,
        "hot_context": None,
    }
    assert route_from_state(state) == "executor"
