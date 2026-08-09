from __future__ import annotations

import dataclasses
import datetime
import os
from collections.abc import Callable

from agent_os.agents.cli_architect import build_cli_architect_invoker
from agent_os.brief import generate_brief, write_brief
from agent_os.connectors import (
    GbrainConnector,
    MarkdownVaultConnector,
    MemoryConnector,
)
from agent_os.llm import get_architect_llm
from agent_os.sandbox import get_sandbox_root
from agent_os.sessions import list_sessions


@dataclasses.dataclass
class BriefExecutionResult:
    date: str
    content: str
    ref: str | None = None


def resolve_brief_connector(name: str | None = None) -> MemoryConnector:
    connector_name = name or os.environ.get("AGENT_OS_MEMORY_CONNECTOR", "")
    if connector_name == "gbrain":
        return GbrainConnector()

    vault_path = os.environ.get("AGENT_OS_VAULT_PATH")
    if not vault_path:
        vault_path = str(get_sandbox_root())

    return MarkdownVaultConnector(vault_path)


def build_brief_summarizer(model: str | None = None) -> Callable[[str], str]:
    model_name = model or os.getenv("LLM_ARCHITECT") or "cli/claude-code"

    if model_name.startswith("cli/"):
        tool_name = model_name[4:]
        invoker = build_cli_architect_invoker(tool_name)

        def cli_summarizer(prompt: str) -> str:
            result = invoker({"task": prompt, "messages": []})
            return result.summary

        return cli_summarizer

    llm = get_architect_llm(model_name)

    def api_summarizer(prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        response = llm.invoke([HumanMessage(content=prompt)])
        return str(response.content) if hasattr(response, "content") else str(response)

    return api_summarizer


def execute_brief(
    *,
    date: str | None = None,
    connector_name: str | None = None,
    write: bool = True
) -> BriefExecutionResult:
    if date is None:
        date = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")

    connector = resolve_brief_connector(connector_name)
    sessions = list_sessions()
    summarizer = build_brief_summarizer()

    brief_md = generate_brief(
        connector,
        sessions,
        date=date,
        summarizer=summarizer
    )

    ref = None
    if write and hasattr(connector, "write_note"):
        write_result = write_brief(connector, brief_md, date)
        ref = write_result.ref if hasattr(write_result, "ref") else str(write_result)

    return BriefExecutionResult(
        date=date,
        content=brief_md,
        ref=ref
    )
