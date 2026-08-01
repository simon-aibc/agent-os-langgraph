from typing import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent_os.nodes.architect import architect_node
from agent_os.nodes.executor import executor_node
from agent_os.nodes.planner import planner_node
from agent_os.nodes.supervisor import supervisor_node
from agent_os.nodes.tool_dispatcher import tool_dispatcher_node
from agent_os.routing import DEFAULT_RUNTIME_CONFIG, ROUTE_TO_NODE, route_from_state
from agent_os.state import SimonState


def build_graph(architect_node_impl: Callable[[SimonState], dict] | None = None) -> CompiledStateGraph:
    """
    Builds and compiles the core graph skeleton.
    The six-step runtime safety bound can be supplied with
    graph.invoke(state, DEFAULT_RUNTIME_CONFIG).
    """
    builder = StateGraph(SimonState)

    if architect_node_impl is None:
        architect_node_impl = architect_node

    # Add nodes
    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("architect", architect_node_impl)
    builder.add_node("executor", executor_node)
    builder.add_node("tool_dispatcher", tool_dispatcher_node)

    # Core flow
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "supervisor")

    # Dynamic routing
    builder.add_conditional_edges("supervisor", route_from_state, ROUTE_TO_NODE)

    # R3: architect routes back to supervisor
    builder.add_edge("architect", "supervisor")

    # Placeholders map to END
    builder.add_edge("executor", END)
    builder.add_edge("tool_dispatcher", END)

    return builder.compile()


graph = build_graph()
