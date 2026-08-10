import os
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent_os import runs
from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB
from agent_os.cli.app import _pending_interrupt
from agent_os.sandbox import sandbox_scope


def _is_node_event(event_type: object, name: object) -> bool:
    return (
        event_type in {"on_chain_start", "on_chain_end"}
        and isinstance(name, str)
        and name not in {"LangGraph", "__start__"}
    )


def _append_stream_event(run_id: str, event: dict[str, Any]) -> None:
    event_type = event.get("event")
    name = event.get("name")
    if _is_node_event(event_type, name):
        runs.append_event(run_id, "node", {"name": name, "event": event_type})
        return

    if event_type == "on_chat_model_stream":
        data = event.get("data")
        if not isinstance(data, dict):
            return
        chunk = data.get("chunk")
        content = getattr(chunk, "content", None)
        if content:
            runs.append_event(run_id, "token", {"content": content})


async def execute_run(
    run_id: str,
    thread_id: str,
    task: str,
    *,
    resume_feedback: str | None = None,
) -> None:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from agent_os.graph import build_graph

    db_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        run = runs.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id} does not exist")
        runs.set_status(run_id, "running")
        with sandbox_scope(run.get("workspace")):
            async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
                # Match the ledger's busy_timeout so the async checkpointer waits for
                # the shared-file write lock instead of failing with "database is
                # locked" when the synchronous ledger is mid-write.
                await saver.conn.execute("PRAGMA busy_timeout=30000")
                graph = build_graph(checkpointer=saver)
                graph_input: object
                if resume_feedback is None:
                    from agent_os.bindings import resolve_backend_binding
                    graph_input = {
                        "messages": [HumanMessage(content=task)],
                        "task": task,
                        "plan": None,
                        "executor_output": None,
                        "human_feedback": None,
                        "hot_context": None,
                        "conversation_summary": None,
                        "backend_binding": resolve_backend_binding(None),
                    }
                else:
                    graph_input = Command(resume=resume_feedback)

                async for event in graph.astream_events(graph_input, config, version="v1"):
                    if isinstance(event, dict):
                        _append_stream_event(run_id, event)

                snapshot = await graph.aget_state(config)
                interrupt_prompt = _pending_interrupt(snapshot)
                if interrupt_prompt is not None:
                    runs.append_event(
                        run_id,
                        "interrupt",
                        {"prompt": str(interrupt_prompt)},
                    )
                    runs.set_status(run_id, "interrupted")
                else:
                    runs.append_event(run_id, "result", {})
                    runs.set_status(run_id, "completed", ended=True)
    except Exception as error:
        message = str(error)
        runs.append_event(run_id, "error", {"message": message})
        runs.set_status(run_id, "error", error=message, ended=True)
