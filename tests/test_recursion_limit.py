import pytest
from langgraph.errors import GraphRecursionError

from agent_os.graph import build_graph
from agent_os.routing import DEFAULT_RUNTIME_CONFIG


def test_recursion_limit_enforced():
    """Prove the six-step runtime bound is actually applied."""

    # Injects an architect node that returns nothing,
    # causing an infinite architect <-> supervisor loop
    # because 'plan' never becomes an ArchitectBrief.
    def looping_architect_node(state):
        return {}

    graph = build_graph(architect_node_impl=looping_architect_node)

    state = {
        "messages": [],
        "task": "infinite loop task",
        "plan": None,
        "executor_output": None,
        "approval": False,
        "hot_context": None,
    }
    assert set(state) == {
        "messages",
        "task",
        "plan",
        "executor_output",
        "approval",
        "hot_context",
    }

    with pytest.raises(GraphRecursionError):
        graph.invoke(state, config=DEFAULT_RUNTIME_CONFIG)
