import pytest
from pydantic import TypeAdapter, ValidationError

from agent_os.graph import build_graph
from agent_os.state import SimonState


def test_simon_state_keys():
    """1. SimonState exposes exactly the six required keys."""
    # TypedDict.__annotations__ gives the keys and types
    expected_keys = {"messages", "task", "plan", "executor_output", "approval", "hot_context"}
    assert set(SimonState.__annotations__.keys()) == expected_keys
    # Also verify they are required (in Python 3.11+, typed dicts require all fields by default unless NotRequired is used)
    assert set(SimonState.__required_keys__) == expected_keys


def test_simon_state_validation_success():
    """2. Pydantic TypeAdapter(SimonState) accepts a complete valid state."""
    adapter = TypeAdapter(SimonState)
    valid_state = {
        "messages": [],
        "task": "Do something",
        "plan": "My plan",
        "executor_output": "Success",
        "approval": True,
        "hot_context": "Some context"
    }
    # Should not raise exception
    validated = adapter.validate_python(valid_state)
    assert validated["task"] == "Do something"


def test_simon_state_validation_failure():
    """3. Validation rejects a state missing a required key."""
    adapter = TypeAdapter(SimonState)
    invalid_state = {
        "messages": [],
        "task": "Do something",
        "plan": "My plan",
        # Missing other keys
    }
    with pytest.raises(ValidationError):
        adapter.validate_python(invalid_state)


def test_build_graph_compiles():
    """4. build_graph() compiles without error."""
    graph = build_graph()
    assert graph is not None

    g = graph.get_graph()
    expected_nodes = {
        "__start__", "planner", "supervisor",
        "architect", "executor", "tool_dispatcher", "__end__"
    }
    assert set(g.nodes.keys()) == expected_nodes

    edges = {(e.source, e.target) for e in g.edges}
    expected_edges = {
        ("__start__", "planner"),
        ("planner", "supervisor"),
        ("supervisor", "architect"),
        ("supervisor", "executor"),
        ("supervisor", "tool_dispatcher"),
        ("supervisor", "__end__"),
        ("architect", "__end__"),
        ("executor", "__end__"),
        ("tool_dispatcher", "__end__")
    }
    assert edges == expected_edges


def test_graph_invocation():
    """5. Invoking the compiled graph with a valid initial state completes and sets plan equal to task while preserving the other state values."""
    graph = build_graph()
    initial_state = {
        "messages": [],
        "task": "Test task",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "hot_context": None
    }

    # Run the graph
    result = graph.invoke(initial_state)

    # Assert values
    assert result["task"] == "Test task"
    assert result["plan"] == "Test task"
    assert result["executor_output"] is None
    assert result["approval"] is None
    assert result["hot_context"] is None
    assert result["messages"] == []
