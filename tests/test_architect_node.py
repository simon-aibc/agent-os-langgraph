from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from agent_os.nodes.architect import architect_node
from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState


def make_state(human_feedback: str | None = None) -> SimonState:
    return {
        "messages": [],
        "task": "do architecture",
        "plan": None,
        "executor_output": None,
        "human_feedback": human_feedback,
        "hot_context": None,
    }


@patch("agent_os.nodes.architect.build_architect_agent")
def test_architect_node_logic(mock_build_agent):
    """Test architect_node wrapper logic directly."""
    mock_agent = MagicMock()
    mock_build_agent.return_value = mock_agent

    brief = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")
    # Simulate a successful structured response from LangGraph
    mock_agent.invoke.return_value = {"structured_response": brief}

    result = architect_node(make_state())

    mock_build_agent.assert_called_once()
    mock_agent.invoke.assert_called_once_with({"messages": [HumanMessage(content="do architecture")]})
    assert result == {"plan": brief}


@patch("agent_os.nodes.architect.build_architect_agent")
def test_architect_node_feedback_handling(mock_build_agent):
    mock_agent = MagicMock()
    mock_build_agent.return_value = mock_agent
    brief = ArchitectBrief(files=["f1"], changes=["c1"], verify_cmd="v1")
    mock_agent.invoke.return_value = {"structured_response": brief}

    # 1. no feedback preserves current prompt
    architect_node(make_state())
    mock_agent.invoke.assert_called_with({"messages": [HumanMessage(content="do architecture")]})

    # 2. approved feedback is not treated as revision feedback
    architect_node(make_state("approved"))
    mock_agent.invoke.assert_called_with({"messages": [HumanMessage(content="do architecture")]})

    # 3. rejected feedback is included verbatim
    architect_node(make_state("rejected: bad plan!"))
    expected_prompt = (
        "do architecture\n\n"
        "Previous plan was rejected with feedback:\n"
        "rejected: bad plan!"
    )
    mock_agent.invoke.assert_called_with({"messages": [HumanMessage(content=expected_prompt)]})
