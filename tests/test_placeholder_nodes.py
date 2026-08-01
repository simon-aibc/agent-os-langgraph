from agent_os.nodes import tool_dispatcher_node


def test_tool_dispatcher_node_preserves_state():
    """Tool dispatcher node placeholder should return an empty dict."""
    state = {"task": "test"}
    result = tool_dispatcher_node(state)  # type: ignore
    assert result == {}
