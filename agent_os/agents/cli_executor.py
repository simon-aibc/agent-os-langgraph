from collections.abc import Callable

from agent_os.backends import get_default_backend_registry
from agent_os.schemas import ArchitectBrief, ExecutorReport
from agent_os.state import SimonState


def build_executor_prompt(plan: ArchitectBrief) -> str:
    """Build the prompt for the executor CLI."""
    prompt = (
        "You are an executor agent. Apply the following approved architectural "
        "plan inside the current sandbox directory. Do NOT access or modify any "
        "files outside the current working directory.\n\n"
        "Approved Plan:\n"
        f"{plan.model_dump_json(indent=2)}\n\n"
    )

    if plan.verify_cmd:
        prompt += (
            f"After making the changes, you MUST run the following verification command:\n"
            f"`{plan.verify_cmd}`\n\n"
        )
    else:
        prompt += "No verification command was provided.\n\n"

    prompt += (
        "Return an ExecutorReport with your results. "
        "Set success to true only if all changes were applied and the verification passed."
    )

    return prompt


def build_cli_executor_invoker(backend: str) -> Callable[[SimonState], ExecutorReport]:
    """
    Returns a callable that executes the CLI executor node logic for a specific backend.
    Supported backends: 'claude-code', 'codex'.
    """
    try:
        adapter = get_default_backend_registry().resolve("executor", backend)
    except ValueError as exc:
        raise ValueError(f"Unsupported CLI executor backend: {backend}. {exc}") from exc
    return adapter.build_invoker("executor")
