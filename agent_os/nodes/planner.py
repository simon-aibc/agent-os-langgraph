from agent_os.state import SimonState


def planner_node(state: SimonState) -> dict:
    """
    Planner node stub.
    Echoes the current task as the plan.
    """
    return {"plan": state["task"]}
