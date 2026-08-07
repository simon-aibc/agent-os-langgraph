from agent_os.schemas import ArchitectBrief, PlanArtifact
from agent_os.state import SimonState


def planner_node(state: SimonState) -> dict:
    """
    Planner node stub.
    Echoes the current task as the plan.
    Preserves an existing ArchitectBrief or PlanArtifact.
    """
    if isinstance(state.get("plan"), (ArchitectBrief, PlanArtifact)):
        return {}
    return {"plan": state["task"]}
