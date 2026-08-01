from typing import Literal

from langgraph.graph import END

from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState

Route = Literal["architect", "executor", "tool", "end"]

ROUTE_TO_NODE: dict[str, str] = {
    "architect": "architect",
    "executor": "executor",
    "tool": "tool_dispatcher",
    "end": END,
}

DEFAULT_RECURSION_LIMIT = 6
DEFAULT_RUNTIME_CONFIG = {"recursion_limit": DEFAULT_RECURSION_LIMIT}

# Tier-1 substring-matching stub.
# It can produce false positives such as "readme" or "researching".
# R7 replaces it with the deterministic registry plus LLM classifier.
KNOWN_SKILLS = ("search", "read", "write", "fetch")


def route_from_state(state: SimonState) -> Route:
    """Determine the next logical step."""
    task_lower = state.get("task", "").lower()

    # 1. skill-first precedence
    if any(skill in task_lower for skill in KNOWN_SKILLS):
        return "tool"

    # 2. if executor_output is present
    if state.get("executor_output") is not None:
        return "end"

    # 3. if approval is True
    if state.get("approval") is True:
        return "executor"

    # R3 Termination rule:
    # If plan is already ArchitectBrief and approval is not True, route end.
    if isinstance(state.get("plan"), ArchitectBrief):
        return "end"

    # 4. otherwise return architect
    return "architect"
