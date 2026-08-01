from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState


def planner_node(state: SimonState) -> dict:
    """
    Planner node stub.
    Echoes the current task as the plan.
    Preserves an existing ArchitectBrief.
    """
    if isinstance(state.get("plan"), ArchitectBrief):
        return {}
    return {"plan": state["task"]}
