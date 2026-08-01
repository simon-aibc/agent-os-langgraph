from agent_os.agents.architect import build_architect_agent
from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState


def architect_node(state: SimonState) -> dict:
    """Architect node wrapper that invokes the ReAct agent."""
    agent = build_architect_agent()
    result = agent.invoke({"messages": [("user", state["task"])]})

    brief = result.get("structured_response")
    if not isinstance(brief, ArchitectBrief):
        raise ValueError("Architect agent did not return a valid ArchitectBrief")

    return {"plan": brief}
