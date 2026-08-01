from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from agent_os.schemas import ArchitectBrief, ExecutorReport

PlanArtifact = str | ArchitectBrief
ExecutorArtifact = str | ExecutorReport


class SimonState(TypedDict):
    """
    State for the SimonOS agent graph.
    """
    messages: Annotated[list[AnyMessage], add_messages]
    task: str
    plan: PlanArtifact | None
    executor_output: ExecutorArtifact | None
    # Deprecated after R5: Use human_feedback instead.
    approval: bool | None
    human_feedback: str | None
    hot_context: str | None
