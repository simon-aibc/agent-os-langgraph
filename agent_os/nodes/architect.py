import os

from agent_os.agents.architect import build_architect_agent
from agent_os.agents.cli_architect import build_cli_architect_invoker
from agent_os.llm import invoke_with_llm_retry
from agent_os.messages import trim_agent_messages
from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState


def architect_node(state: SimonState) -> dict[str, ArchitectBrief]:
    """Architect node wrapper that invokes the ReAct agent."""
    prompt = state["task"]
    feedback = state.get("human_feedback")
    if feedback and feedback.startswith("rejected:"):
        prompt += f"\n\nPrevious plan was rejected with feedback:\n{feedback}"

    trimmed = trim_agent_messages(state.get("messages", []), prompt)

    llm_architect = os.getenv("LLM_ARCHITECT", "")
    if llm_architect.startswith("cli/"):
        backend = llm_architect[4:]
        invoker = build_cli_architect_invoker(backend)

        # Pass a copied state containing trimmed messages; do not mutate input state
        copied_state = dict(state)
        copied_state["messages"] = trimmed
        brief = invoker(copied_state)
        return {"plan": brief}

    agent = build_architect_agent()
    result = invoke_with_llm_retry(lambda: agent.invoke({"messages": trimmed}))

    brief = result.get("structured_response")
    if not isinstance(brief, ArchitectBrief):
        raise ValueError("Architect agent did not return a valid ArchitectBrief")

    return {"plan": brief}
