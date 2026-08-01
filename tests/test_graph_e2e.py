from agent_os.graph import build_graph
from agent_os.routing import DEFAULT_RUNTIME_CONFIG
from agent_os.schemas import ArchitectBrief, ExecutorReport

# A fake architect node for tests that does not use the LLM API
def fake_architect_node(state):
    # Simulate the future R5 approval seam after the architect produces a plan.
    return {"plan": ArchitectBrief(files=["dummy.py"], changes=["dummy change"], verify_cmd="dummy"), "approval": True}

def fake_executor_node(state):
    return {"executor_output": ExecutorReport(diff="foo", verify_output="ok", success=True)}


def test_build_graph_compiles():
    graph = build_graph(architect_node_impl=fake_architect_node, executor_node_impl=fake_executor_node)
    nodes = {node for node in graph.nodes if node != "__start__"}
    assert nodes == {"planner", "supervisor", "architect", "executor", "tool_dispatcher"}


def test_graph_e2e_normal_task():
    graph = build_graph(architect_node_impl=fake_architect_node, executor_node_impl=fake_executor_node)

    state = {
        "task": "do something normal",
        "plan": None,
        "messages": [],
        "executor_output": None,
        "approval": False,
        "hot_context": None,
    }

    # Run the graph and collect nodes
    visited = []
    for step in graph.stream(state, config=DEFAULT_RUNTIME_CONFIG):
        visited.append(list(step.keys())[0])

    # START -> planner -> supervisor -> architect -> supervisor (sees approval=True) -> executor -> supervisor (sees success=True) -> END
    assert visited == ["planner", "supervisor", "architect", "supervisor", "executor", "supervisor"]


def test_graph_e2e_skill_task():
    graph = build_graph(architect_node_impl=fake_architect_node, executor_node_impl=fake_executor_node)
    state = {
        "task": "please search for something",
        "plan": None,
        "messages": [],
        "executor_output": None,
        "approval": False,
        "hot_context": None,
    }
    visited = []
    for step in graph.stream(state, config=DEFAULT_RUNTIME_CONFIG):
        visited.append(list(step.keys())[0])

    # tool_dispatcher maps to END in our placeholder routing
    assert visited == ["planner", "supervisor", "tool_dispatcher"]


def test_graph_e2e_approval_true():
    graph = build_graph(architect_node_impl=fake_architect_node, executor_node_impl=fake_executor_node)
    state = {
        "task": "do it",
        "plan": ArchitectBrief(files=[], changes=[], verify_cmd=""),
        "messages": [],
        "executor_output": None,
        "approval": True,
        "hot_context": None,
    }
    visited = []
    for step in graph.stream(state, config=DEFAULT_RUNTIME_CONFIG):
        visited.append(list(step.keys())[0])

    assert visited == ["planner", "supervisor", "executor", "supervisor"]


def test_graph_e2e_executor_output_present():
    graph = build_graph(architect_node_impl=fake_architect_node, executor_node_impl=fake_executor_node)
    state = {
        "task": "do it",
        "plan": ArchitectBrief(files=[], changes=[], verify_cmd=""),
        "messages": [],
        "executor_output": ExecutorReport(diff="", verify_output="", success=True),
        "approval": True,
        "hot_context": None,
    }
    visited = []
    for step in graph.stream(state, config=DEFAULT_RUNTIME_CONFIG):
        visited.append(list(step.keys())[0])

    # supervisor sees executor_output and routes to END
    assert visited == ["planner", "supervisor"]
