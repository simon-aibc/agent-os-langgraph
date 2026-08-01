from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent_os.nodes.planner import planner_node
from agent_os.nodes.supervisor import supervisor_node
from agent_os.state import SimonState


def build_graph() -> CompiledStateGraph:
    """Builds and compiles the core graph skeleton."""
    builder = StateGraph(SimonState)
    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", supervisor_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "supervisor")
    builder.add_edge("supervisor", END)

    return builder.compile()


graph = build_graph()
