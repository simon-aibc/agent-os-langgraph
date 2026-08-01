from typing import Literal

from langgraph.graph import END

from agent_os.schemas import ArchitectBrief, ExecutorReport
from agent_os.state import SimonState

Route = Literal["architect", "executor", "tool", "end"]

ROUTE_TO_NODE: dict[str, str] = {
    "architect": "architect",
    "executor": "executor",
    "tool": "tool_dispatcher",
    "end": END,
}

# Six executed nodes plus LangGraph's final termination superstep.
DEFAULT_RECURSION_LIMIT = 7
DEFAULT_RUNTIME_CONFIG = {"recursion_limit": DEFAULT_RECURSION_LIMIT}

# Tier-1 substring-matching stub.
# It can produce false positives such as "readme" or "researching".
# R7 replaces it with the deterministic registry plus LLM classifier.
KNOWN_SKILLS = ("search", "read", "write", "fetch")


def route_from_state(state: SimonState) -> Route:
    executor_output = state.get("executor_output")
    if isinstance(executor_output, ExecutorReport) and executor_output.success is True:
        return "end"

    task_lower = state["task"].lower()
    if any(skill in task_lower for skill in KNOWN_SKILLS):
        return "tool"

    if isinstance(executor_output, str):
        return "end"

    if state.get("approval") is True:
        return "executor"

    if isinstance(state.get("plan"), ArchitectBrief):
        return "end"

    return "architect"
