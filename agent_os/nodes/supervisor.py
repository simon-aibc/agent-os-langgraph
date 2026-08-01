from langgraph.types import Command

from agent_os.routing import ROUTE_TO_NODE, route_from_state
from agent_os.state import SimonState


def supervisor_node(state: SimonState) -> Command:
    """
    Supervisor node.
    Determines the logical R2 route using route_from_state, then returns a
    Command routing to the resolved graph target using ROUTE_TO_NODE.
    """
    route = route_from_state(state)
    return Command(goto=ROUTE_TO_NODE[route])
