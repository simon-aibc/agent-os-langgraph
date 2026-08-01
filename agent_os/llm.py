import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_litellm import ChatLiteLLM


def get_architect_llm(model_name: str | None = None) -> BaseChatModel:
    """
    Get the configured architect LLM.
    Resolves model_name explicitly first, then falls back to LLM_ARCHITECT
    environment variable.
    """
    resolved_model = model_name or os.getenv("LLM_ARCHITECT")
    if not resolved_model:
        raise ValueError("No architect model configured. Pass model_name or set LLM_ARCHITECT.")

    return ChatLiteLLM(model=resolved_model)
