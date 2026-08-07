import os

from agent_os.agents.architect import build_architect_agent
from agent_os.agents.cli_architect import build_cli_architect_invoker
from agent_os.llm import invoke_with_llm_retry
from agent_os.messages import trim_agent_messages
from agent_os.schemas import ArchitectBrief, PlanArtifact
from agent_os.state import SimonState


def architect_node(state: SimonState) -> dict[str, ArchitectBrief]:
    """Architect node wrapper that invokes the ReAct agent."""
    prompt = state["task"]
    feedback = state.get("human_feedback")
    if feedback and feedback.startswith("rejected:"):
        prompt += f"\n\nPrevious plan was rejected with feedback:\n{feedback}"
        
    hot_context = state.get("hot_context")
    if hot_context is None:
        hot_context = ""
        binding = state.get("backend_binding")
        if binding:
            from pathlib import Path

            from agent_os.backends import BackendRegistry
            from agent_os.profiles import load_profiles, resolve_profile
            try:
                profile_file = load_profiles()
                registry = BackendRegistry()
                resolved_prof = resolve_profile(profile_file, binding.profile_name, registry, Path(binding.sandbox_root))
                config = resolved_prof.hot_context
                
                connector_name = os.getenv("AGENT_OS_MEMORY_CONNECTOR", "markdown")
                from agent_os.connectors import GbrainConnector, MarkdownVaultConnector
                
                if connector_name == "gbrain":
                    connector = GbrainConnector()
                else:
                    vault_path = os.getenv("AGENT_OS_VAULT_PATH", binding.sandbox_root)
                    connector = MarkdownVaultConnector(vault_path)
                    
                from agent_os.hot_context import load_hot_context
                hot_context = load_hot_context(
                    connector,
                    max_chars=config.max_chars,
                    max_age_days=config.max_age_days,
                    sources=config.sources
                )
            except Exception:
                pass
                
    if hot_context:
        prompt = f"{prompt}\n\n## Context (from vault)\n{hot_context}"

    trimmed = trim_agent_messages(state.get("messages", []), prompt)

    llm_architect = os.getenv("LLM_ARCHITECT", "")
    if llm_architect.startswith("cli/"):
        backend = llm_architect[4:]
        invoker = build_cli_architect_invoker(backend)

        # Pass a copied state containing trimmed messages; do not mutate input state
        copied_state = dict(state)
        copied_state["messages"] = trimmed
        brief = invoke_with_llm_retry(lambda: invoker(copied_state))
        return {"plan": brief, "hot_context": hot_context}

    agent = build_architect_agent()
    result = invoke_with_llm_retry(lambda: agent.invoke({"messages": trimmed}))

    brief = result.get("structured_response")
    if not isinstance(brief, (ArchitectBrief, PlanArtifact)):
        raise ValueError("Architect agent did not return a valid PlanArtifact or ArchitectBrief")

    return {"plan": brief, "hot_context": hot_context}
