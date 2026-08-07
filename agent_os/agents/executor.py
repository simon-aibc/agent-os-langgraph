from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from agent_os.llm import get_executor_llm, prepare_system_prompt
from agent_os.schemas import CodingResult
from agent_os.tools import bash, edit_file, run_tests

SYSTEM_PROMPT = """
You are the system Executor.
- Follow the supplied PlanArtifact exactly.
- Operate only through sandboxed tools (edit_file, bash, run_tests).
- Never access paths outside AGENT_OS_SANDBOX.
- Run the supplied verification command using bash or run_tests (if provided).
- Report diff, verify_output, and status in your final response.
"""


def build_executor_agent(llm: BaseChatModel | None = None) -> CompiledStateGraph:
    """Build the executor ReAct sub-graph."""
    resolved_llm = llm if llm is not None else get_executor_llm()

    tools = [edit_file, bash, run_tests]
    system_prompt = prepare_system_prompt(SYSTEM_PROMPT, resolved_llm)

    return create_agent(
        model=resolved_llm,
        tools=tools,
        system_prompt=system_prompt,
        response_format=CodingResult,
        name="executor_react_agent",
    )
