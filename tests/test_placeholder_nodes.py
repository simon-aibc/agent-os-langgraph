from agent_os.nodes import architect_node, executor_node, tool_dispatcher_node


def test_architect_node_preserves_state():
    """Architect node placeholder should return an empty dict."""
    state = {"task": "test"}
    result = architect_node(state)  # type: ignore
    assert result == {}


def test_executor_node_preserves_state():
    """Executor node placeholder should return an empty dict."""
    state = {"task": "test"}
    result = executor_node(state)  # type: ignore
    assert result == {}


def test_tool_dispatcher_node_preserves_state():
    """Tool dispatcher node placeholder should return an empty dict."""
    state = {"task": "test"}
    result = tool_dispatcher_node(state)  # type: ignore
    assert result == {}
