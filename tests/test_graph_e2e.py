from agent_os.graph import build_graph
from agent_os.schemas import ArchitectBrief

# A fake architect node for tests that does not use the LLM API
def fake_architect_node(state):
    return {"plan": ArchitectBrief(files=["dummy.py"], changes=["dummy change"], verify_cmd="dummy")}


def test_build_graph_compiles():
    graph = build_graph(architect_node_impl=fake_architect_node)
    nodes = {node for node in graph.nodes if node != "__start__"}
    assert nodes == {"planner", "supervisor", "architect", "executor", "tool_dispatcher"}

    # architect now routes back to supervisor
    # so we'll check it in the e2e test, or we can check the edges directly


def test_graph_e2e_normal_task():
    graph = build_graph(architect_node_impl=fake_architect_node)

    config = {"recursion_limit": 6}
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
    for step in graph.stream(state, config=config):
        visited.append(list(step.keys())[0])

    # START -> planner -> supervisor -> architect -> supervisor -> END
    assert visited == ["planner", "supervisor", "architect", "supervisor"]


def test_graph_e2e_skill_task():
    graph = build_graph(architect_node_impl=fake_architect_node)
    config = {"recursion_limit": 6}
    state = {
        "task": "please search for something",
        "plan": None,
        "messages": [],
        "executor_output": None,
        "approval": False,
        "hot_context": None,
    }
    visited = []
    for step in graph.stream(state, config=config):
        visited.append(list(step.keys())[0])

    # tool_dispatcher maps to END in our placeholder routing
    assert visited == ["planner", "supervisor", "tool_dispatcher"]


def test_graph_e2e_approval_true():
    graph = build_graph(architect_node_impl=fake_architect_node)
    config = {"recursion_limit": 6}
    state = {
        "task": "do it",
        "plan": ArchitectBrief(files=[], changes=[], verify_cmd=""),
        "messages": [],
        "executor_output": None,
        "approval": True,
        "hot_context": None,
    }
    visited = []
    for step in graph.stream(state, config=config):
        visited.append(list(step.keys())[0])

    assert visited == ["planner", "supervisor", "executor"]


def test_graph_e2e_executor_output_present():
    graph = build_graph(architect_node_impl=fake_architect_node)
    config = {"recursion_limit": 6}
    state = {
        "task": "do it",
        "plan": ArchitectBrief(files=[], changes=[], verify_cmd=""),
        "messages": [],
        "executor_output": "done",
        "approval": True,
        "hot_context": None,
    }
    visited = []
    for step in graph.stream(state, config=config):
        visited.append(list(step.keys())[0])

    # supervisor sees executor_output and routes to END
    assert visited == ["planner", "supervisor"]
