from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from agent_os.schemas import ArchitectBrief


class SimonState(TypedDict):
    """
    State for the SimonOS agent graph.
    """
    messages: Annotated[list[AnyMessage], add_messages]
    task: str
    plan: str | ArchitectBrief | None
    executor_output: str | None
    approval: bool | None
    hot_context: str | None
