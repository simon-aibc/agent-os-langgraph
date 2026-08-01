import os
from unittest.mock import patch

import pytest

from agent_os.llm import get_architect_llm, get_executor_llm


def test_get_architect_llm_missing_config(monkeypatch):
    """Missing configuration raises ValueError."""
    monkeypatch.delenv("LLM_ARCHITECT", raising=False)
    with pytest.raises(ValueError, match="No architect model configured"):
        get_architect_llm()


@patch("agent_os.llm.ChatLiteLLM")
def test_get_architect_llm_explicit_model(mock_chat, monkeypatch):
    """Explicit model_name takes precedence over environment variable."""
    monkeypatch.setenv("LLM_ARCHITECT", "anthropic/claude-3-haiku-20240307")

    get_architect_llm(model_name="openai/gpt-4o")

    mock_chat.assert_called_once_with(model="openai/gpt-4o")


@patch("agent_os.llm.ChatLiteLLM")
def test_get_executor_llm_missing_config(mock_chat_lite_llm, monkeypatch):
    """Missing configuration raises ValueError."""
    monkeypatch.delenv("LLM_EXECUTOR", raising=False)
    with pytest.raises(ValueError, match="No executor model configured"):
        get_executor_llm()


@patch("agent_os.llm.ChatLiteLLM")
def test_get_executor_llm_explicit_model(mock_chat_lite_llm, monkeypatch):
    """Explicit model_name takes precedence over environment."""
    monkeypatch.setenv("LLM_EXECUTOR", "env-model")
    llm = get_executor_llm(model_name="explicit-model")
    assert llm == mock_chat_lite_llm.return_value
    mock_chat_lite_llm.assert_called_once_with(model="explicit-model")


@patch("agent_os.llm.ChatLiteLLM")
def test_get_executor_llm_env_model(mock_chat_lite_llm, monkeypatch):
    """Environment value is used when no argument is supplied."""
    monkeypatch.setenv("LLM_EXECUTOR", "env-model")
    llm = get_executor_llm()
    assert llm == mock_chat_lite_llm.return_value
    mock_chat_lite_llm.assert_called_once_with(model="env-model")


@patch("agent_os.llm.ChatLiteLLM")
def test_get_architect_llm_env_fallback(mock_chat, monkeypatch):
    """Environment value is used when no argument is supplied."""
    monkeypatch.setenv("LLM_ARCHITECT", "anthropic/claude-3-5-sonnet-20240620")

    get_architect_llm()

    mock_chat.assert_called_once_with(model="anthropic/claude-3-5-sonnet-20240620")
