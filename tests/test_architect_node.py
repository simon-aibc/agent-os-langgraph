from unittest.mock import MagicMock, patch

from agent_os.nodes.architect import architect_node
from agent_os.schemas import ArchitectBrief


@patch("agent_os.nodes.architect.build_architect_agent")
def test_architect_node_logic(mock_build_agent):
    """Test architect_node wrapper logic directly."""
    mock_agent = MagicMock()
    mock_build_agent.return_value = mock_agent

    brief = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")
    # Simulate a successful structured response from LangGraph
    mock_agent.invoke.return_value = {"structured_response": brief}

    state = {
        "messages": [],
        "task": "do architecture",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "hot_context": None,
    }

    result = architect_node(state)

    mock_build_agent.assert_called_once()
    mock_agent.invoke.assert_called_once_with({"messages": [("user", "do architecture")]})
    assert result == {"plan": brief}
