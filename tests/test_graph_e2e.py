from agent_os.graph import build_graph


def get_executed_nodes(state):
    graph = build_graph()
    steps = list(graph.stream(state))
    # Each step is a dict like {'node_name': state_update}
    return [list(step.keys())[0] for step in steps]


def test_e2e_normal_task():
    """normal task routes supervisor -> architect -> END"""
    state = {
        "messages": [],
        "task": "A normal task",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "hot_context": None
    }
    nodes = get_executed_nodes(state)
    assert nodes == ["planner", "supervisor", "architect"]


def test_e2e_known_skill():
    """known skill task routes supervisor -> tool_dispatcher -> END"""
    state = {
        "messages": [],
        "task": "Please search for info",
        "plan": None,
        "executor_output": None,
        "approval": None,
        "hot_context": None
    }
    nodes = get_executed_nodes(state)
    assert nodes == ["planner", "supervisor", "tool_dispatcher"]


def test_e2e_approval_true():
    """approval=True routes supervisor -> executor -> END"""
    state = {
        "messages": [],
        "task": "Normal task",
        "plan": "My plan",
        "executor_output": None,
        "approval": True,
        "hot_context": None
    }
    nodes = get_executed_nodes(state)
    assert nodes == ["planner", "supervisor", "executor"]


def test_e2e_executor_output_present():
    """executor_output present routes supervisor -> END"""
    state = {
        "messages": [],
        "task": "Normal task",
        "plan": "My plan",
        "executor_output": "Task completed successfully",
        "approval": None,
        "hot_context": None
    }
    nodes = get_executed_nodes(state)
    assert nodes == ["planner", "supervisor"]
