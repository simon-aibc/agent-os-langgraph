from typing import Any
from unittest.mock import MagicMock, patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent_os.agents.executor import build_executor_agent
from agent_os.schemas import ExecutorReport
from agent_os.tools import bash, edit_file, run_tests


@patch("agent_os.agents.executor.create_agent")
def test_build_executor_agent_factory(mock_create):
    """Test the executor agent factory forwards correct parameters."""
    mock_llm = MagicMock()

    build_executor_agent(llm=mock_llm)

    mock_create.assert_called_once()

    kwargs = mock_create.call_args.kwargs
    assert kwargs["model"] == mock_llm
    assert kwargs["tools"] == [edit_file, bash, run_tests]
    assert kwargs["response_format"] == ExecutorReport
    assert "executor_react_agent" in kwargs.get("name", "")
    assert "sandbox" in kwargs["system_prompt"].lower()
    assert "architectbrief" in kwargs["system_prompt"].lower()
    assert "diff" in kwargs["system_prompt"].lower()


class DeterministicFakeExecutorLLM(BaseChatModel):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "ExecutorReport",
                    "args": {
                        "diff": "mock diff",
                        "verify_output": "mock verify",
                        "success": True,
                    },
                    "id": "executor-report-1",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "deterministic-executor-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def test_executor_agent_e2e_fake_llm():
    """Invoke the real executor sub-graph with a deterministic mock chat model."""
    fake_llm = DeterministicFakeExecutorLLM()
    agent = build_executor_agent(llm=fake_llm)

    result = agent.invoke({"messages": [("user", "Execute this ArchitectBrief")]})

    assert "structured_response" in result
    report = result["structured_response"]
    assert isinstance(report, ExecutorReport)
    assert report.diff == "mock diff"
    assert report.verify_output == "mock verify"
    assert report.success is True
