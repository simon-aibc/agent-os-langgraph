from collections.abc import Sequence

from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage
from langchain_core.messages.utils import trim_messages

AGENT_MESSAGE_MAX_TOKENS = 8000


def trim_agent_messages(
    state_messages: Sequence[AnyMessage],
    new_prompt: str,
) -> list[BaseMessage]:
    """Include the current prompt once and bound context sent to an agent."""
    messages = list(state_messages)
    if not (
        messages
        and isinstance(messages[-1], HumanMessage)
        and messages[-1].content == new_prompt
    ):
        messages.append(HumanMessage(content=new_prompt))

    return trim_messages(
        messages,
        max_tokens=AGENT_MESSAGE_MAX_TOKENS,
        token_counter="approximate",
        strategy="last",
        allow_partial=True,
        start_on="human",
    )
