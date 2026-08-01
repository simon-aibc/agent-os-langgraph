from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent_os.agents.architect import build_architect_agent
from agent_os.schemas import ArchitectBrief
from agent_os.tools import grep, plan_writer, read_file


@patch("agent_os.agents.architect.create_agent")
def test_build_architect_agent_factory(mock_create):
    """Test the architect agent factory forwards correct parameters."""
    mock_llm = MagicMock()

    agent = build_architect_agent(llm=mock_llm)

    mock_create.assert_called_once()

    kwargs = mock_create.call_args.kwargs
    assert kwargs["model"] == mock_llm
    assert kwargs["tools"] == [read_file, grep, plan_writer]
    assert kwargs["response_format"] == ArchitectBrief
    assert "prompt" not in kwargs
    assert "architect_react_agent" in kwargs.get("name", "")
    assert "read-only" in kwargs["system_prompt"].lower()
    assert "inspect" in kwargs["system_prompt"].lower()
    assert "before recommending" in kwargs["system_prompt"].lower()


class DeterministicFakeLLM(BaseChatModel):
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "ArchitectBrief",
                    "args": {
                        "files": ["src/app.py"],
                        "changes": ["Fix bug"],
                        "verify_cmd": "pytest",
                    },
                    "id": "architect-brief-1",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "deterministic-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def test_architect_agent_e2e_fake_llm():
    """Invoke the real architect sub-graph with a deterministic mock chat model."""
    fake_llm = DeterministicFakeLLM()
    agent = build_architect_agent(llm=fake_llm)

    result = agent.invoke({"messages": [("user", "Fix the bug")]})

    # LangGraph returns the structured output in structured_response by default
    assert "structured_response" in result
    brief = result["structured_response"]
    assert isinstance(brief, ArchitectBrief)
    assert brief.files == ["src/app.py"]
    assert brief.changes == ["Fix bug"]
    assert brief.verify_cmd == "pytest"
