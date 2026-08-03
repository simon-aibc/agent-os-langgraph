from unittest.mock import MagicMock, patch

import pytest

from agent_os.cli_backends import CliBackendError
from agent_os.nodes.executor import executor_node
from agent_os.schemas import ArchitectBrief, ExecutorReport


@pytest.fixture(autouse=True)
def clear_cli_executor_backend(monkeypatch):
    monkeypatch.delenv("LLM_EXECUTOR", raising=False)


@patch("agent_os.nodes.executor.build_executor_agent")
def test_executor_node_logic(mock_build_agent):
    """Test executor_node wrapper logic directly."""
    mock_agent = MagicMock()
    mock_build_agent.return_value = mock_agent

    report = ExecutorReport(diff="foo", verify_output="bar", success=True)
    # Simulate a successful structured response from LangGraph
    mock_agent.invoke.return_value = {"structured_response": report}

    brief = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")

    state = {
        "messages": [],
        "task": "do executor",
        "plan": brief,
        "executor_output": None,
        "hot_context": None,
    }

    result = executor_node(state)

    mock_build_agent.assert_called_once()
    mock_agent.invoke.assert_called_once()
    assert result == {"executor_output": report}


def test_executor_node_invalid_plan():
    """Test executor_node raises ValueError if plan is not an ArchitectBrief."""
    state = {
        "messages": [],
        "task": "do executor",
        "plan": "just a string",
        "executor_output": None,
        "hot_context": None,
    }

    with pytest.raises(ValueError, match="Executor requires an ArchitectBrief plan."):
        executor_node(state)


def test_executor_node_cli_backend_routing(monkeypatch):
    """Test executor_node routes to CLI when LLM_EXECUTOR starts with cli/"""
    monkeypatch.setenv("LLM_EXECUTOR", "cli/codex")

    plan = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")
    report = ExecutorReport(diff="d", verify_output="vo", success=True)
    state = {
        "messages": [],
        "task": "do executor",
        "plan": plan,
        "executor_output": None,
        "hot_context": None,
    }

    with patch(
        "agent_os.nodes.executor.build_cli_executor_invoker"
    ) as mock_build_invoker:
        mock_invoker = MagicMock(return_value=report)
        mock_build_invoker.return_value = mock_invoker

        result = executor_node(state)

        mock_build_invoker.assert_called_once_with("codex")
        mock_invoker.assert_called_once()
        passed_state = mock_invoker.call_args[0][0]
        # State passed to CLI invoker is copied and has trimmed messages
        assert passed_state is not state
        assert len(passed_state["messages"]) == 1
        assert (
            "Please execute this ArchitectBrief" in passed_state["messages"][0].content
        )
        assert state["messages"] == []
        assert result == {"executor_output": report}


def test_executor_node_cli_unknown_backend(monkeypatch):
    monkeypatch.setenv("LLM_EXECUTOR", "cli/unknown")
    plan = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")
    state = {
        "messages": [],
        "task": "do",
        "plan": plan,
    }

    with pytest.raises(ValueError, match="Unsupported CLI executor backend"):
        executor_node(state)


def test_executor_node_cli_partial_change_warning(monkeypatch):
    monkeypatch.setenv("LLM_EXECUTOR", "cli/claude-code")
    plan = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")
    state = {
        "messages": [],
        "task": "do",
        "plan": plan,
    }

    def mock_invoker(state):
        raise CliBackendError("Subprocess failed")

    with patch(
        "agent_os.nodes.executor.build_cli_executor_invoker"
    ) as mock_build_invoker:
        mock_build_invoker.return_value = mock_invoker

        with pytest.raises(
            RuntimeError,
            match=r"CLI executor failed \(CliBackendError\)\. Partial sandbox changes",
        ):
            executor_node(state)


def test_executor_node_cli_invalid_output_warns_about_partial_changes(monkeypatch):
    monkeypatch.setenv("LLM_EXECUTOR", "cli/codex")
    plan = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")
    state = {"messages": [], "task": "do", "plan": plan}
    mock_invoker = MagicMock(side_effect=ValueError("invalid structured output"))

    with patch(
        "agent_os.nodes.executor.build_cli_executor_invoker",
        return_value=mock_invoker,
    ):
        with pytest.raises(RuntimeError, match="Partial sandbox changes"):
            executor_node(state)

    mock_invoker.assert_called_once()
