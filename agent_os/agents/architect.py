from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from agent_os.llm import get_architect_llm
from agent_os.schemas import ArchitectBrief
from agent_os.tools import grep, plan_writer, read_file

SYSTEM_PROMPT = """
You are the system Architect.
- Inspect the codebase using grep and read_file before recommending changes.
- Remain read-only; never execute or edit code directly.
- Return a detailed plan using the plan_writer format, including files to modify, changes to make, and a verify_cmd.
"""


def build_architect_agent(llm: BaseChatModel | None = None) -> CompiledStateGraph:
    """Build the architect ReAct sub-graph."""
    resolved_llm = llm if llm is not None else get_architect_llm()

    tools = [read_file, grep, plan_writer]

    return create_agent(
        model=resolved_llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=ArchitectBrief,
        name="architect_react_agent"
    )
