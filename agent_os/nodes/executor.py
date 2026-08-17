import os

from agent_os.agents.cli_executor import build_cli_executor_invoker
from agent_os.agents.executor import build_executor_agent
from agent_os.cli_backends import CliBackendError
from agent_os.llm import invoke_with_llm_retry
from agent_os.messages import trim_agent_messages
from agent_os.schemas import (
    ArchitectBrief,
    ExecutionResult,
    ExecutorReport,
    PlanArtifact,
)
from agent_os.state import SimonState


def _is_quota_or_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    quota_indicators = [
        "hit your usage limit",
        "usage limit",
        "rate limit",
        "purchase more credits",
        "too many requests",
        "insufficient_quota",
        "quota exceeded",
        "429",
    ]
    return any(ind in text for ind in quota_indicators)


def executor_node(state: SimonState) -> dict[str, ExecutorReport]:
    """
    R4 Executor node.
    Requires state["plan"] to be an ArchitectBrief.
    Executes the plan using the sandboxed executor agent.
    Returns ExecutorReport in executor_output.
    """
    plan = state.get("plan")
    if not isinstance(plan, (ArchitectBrief, PlanArtifact)):
        raise ValueError("Executor requires a PlanArtifact or ArchitectBrief plan.")

    user_message = f"Please execute this ArchitectBrief:\n{plan.model_dump_json()}"
    trimmed = trim_agent_messages(state.get("messages", []), user_message)

    llm_executor = os.getenv("LLM_EXECUTOR", "")
    if llm_executor.startswith("cli/"):
        backend = llm_executor[4:]

        invoker = build_cli_executor_invoker(backend)
        copied_state = dict(state)
        copied_state["messages"] = trimmed

        try:
            report = invoker(copied_state)
        except (CliBackendError, ValueError) as exc:
            fallback_backend = os.getenv(
                "LLM_EXECUTOR_FALLBACK",
                "claude-code" if backend == "codex" else "",
            )
            if fallback_backend and _is_quota_or_rate_limit_error(exc):
                fallback_name = (
                    fallback_backend[4:]
                    if fallback_backend.startswith("cli/")
                    else fallback_backend
                )
                try:
                    fallback_invoker = build_cli_executor_invoker(fallback_name)
                    report = fallback_invoker(copied_state)
                    return {"executor_output": report}
                except Exception as fallback_exc:
                    raise RuntimeError(
                        f"CLI executor '{backend}' hit quota limit and fallback '{fallback_name}' also failed: {fallback_exc}"
                    ) from fallback_exc

            raise RuntimeError(
                f"CLI executor failed ({type(exc).__name__}). Partial sandbox "
                "changes may exist and should be inspected before resume. "
                f"Details: {exc}"
            ) from exc

        return {"executor_output": report}

    agent = build_executor_agent()
    result = invoke_with_llm_retry(lambda: agent.invoke({"messages": trimmed}))

    if "structured_response" not in result or not isinstance(
        result["structured_response"], (ExecutorReport, ExecutionResult)
    ):
        raise ValueError("Executor agent failed to return a valid ExecutionResult or ExecutorReport.")

    return {"executor_output": result["structured_response"]}
