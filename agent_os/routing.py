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


def build_runtime_config(thread_id: str) -> dict[str, object]:
    normalized_thread_id = thread_id.strip()
    if not normalized_thread_id:
        raise ValueError("thread_id must not be empty")
    return {
        "recursion_limit": DEFAULT_RECURSION_LIMIT,
        "configurable": {"thread_id": normalized_thread_id},
    }


def route_from_state(state: SimonState) -> Route:
    executor_output = state.get("executor_output")
    human_feedback = state.get("human_feedback")

    # a. successful ExecutorReport -> end
    if isinstance(executor_output, ExecutorReport) and executor_output.success is True:
        return "end"

    # b. human_feedback == "approved" -> executor
    if human_feedback == "approved":
        return "executor"

    # c. human_feedback beginning "rejected:" -> architect
    if human_feedback and human_feedback.startswith("rejected:"):
        return "architect"

    # legacy string executor_output -> end
    if isinstance(executor_output, str):
        return "end"

    # ArchitectBrief without a decision -> end
    if isinstance(state.get("plan"), ArchitectBrief):
        return "end"

    # When router_escalated is True, supervisor must route to architect
    if state.get("router_escalated") is True:
        return "architect"

    # For a new unresolved task -> tool_dispatcher first
    return "tool"
