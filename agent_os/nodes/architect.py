from agent_os.agents.architect import build_architect_agent
from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState


def architect_node(state: SimonState) -> dict[str, ArchitectBrief]:
    """Architect node wrapper that invokes the ReAct agent."""
    agent = build_architect_agent()

    prompt = state["task"]
    feedback = state.get("human_feedback")
    if feedback and feedback.startswith("rejected:"):
        prompt += f"\n\nPrevious plan was rejected with feedback:\n{feedback}"

    result = agent.invoke({"messages": [("user", prompt)]})

    brief = result.get("structured_response")
    if not isinstance(brief, ArchitectBrief):
        raise ValueError("Architect agent did not return a valid ArchitectBrief")

    return {"plan": brief}
