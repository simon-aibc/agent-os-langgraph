from typing import Literal

from langgraph.graph import END

from agent_os.state import SimonState

Route = Literal["architect", "executor", "tool", "end"]

ROUTE_TO_NODE = {
    "architect": "architect",
    "executor": "executor",
    "tool": "tool_dispatcher",
    "end": END,
}

DEFAULT_RECURSION_LIMIT = 6
DEFAULT_RUNTIME_CONFIG = {"recursion_limit": DEFAULT_RECURSION_LIMIT}

KNOWN_SKILLS = ("search", "read", "write", "fetch")


def route_from_state(state: SimonState) -> Route:
    """
    Determine the next route based on the current state.
    """
    task_lower = state["task"].lower()

    # 1. skill-first precedence
    if any(skill in task_lower for skill in KNOWN_SKILLS):
        return "tool"

    # 2. if executor_output is present
    if state.get("executor_output") is not None:
        return "end"

    # 3. if approval is True
    if state.get("approval") is True:
        return "executor"

    # 4. otherwise
    return "architect"
