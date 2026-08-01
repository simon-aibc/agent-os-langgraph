from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from agent_os.llm import get_executor_llm
from agent_os.schemas import ExecutorReport
from agent_os.tools import bash, edit_file, run_tests

SYSTEM_PROMPT = """
You are the system Executor.
- Follow the supplied ArchitectBrief exactly.
- Operate only through sandboxed tools (edit_file, bash, run_tests).
- Never access paths outside AGENT_OS_SANDBOX.
- Run the supplied verification command using bash or run_tests.
- Report diff, verify_output, and success in your final response.
"""


def build_executor_agent(llm: BaseChatModel | None = None) -> CompiledStateGraph:
    """Build the executor ReAct sub-graph."""
    resolved_llm = llm if llm is not None else get_executor_llm()

    tools = [edit_file, bash, run_tests]

    return create_agent(
        model=resolved_llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=ExecutorReport,
        name="executor_react_agent"
    )
