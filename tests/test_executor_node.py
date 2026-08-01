from unittest.mock import MagicMock, patch

import pytest

from agent_os.nodes.executor import executor_node
from agent_os.schemas import ArchitectBrief, ExecutorReport


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
        "approval": True,
        "hot_context": None
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
        "approval": True,
        "hot_context": None
    }

    with pytest.raises(ValueError, match="Executor requires an ArchitectBrief plan."):
        executor_node(state)
