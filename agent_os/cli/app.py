import argparse
import asyncio
import datetime as dt
import os
import sys
import traceback
import uuid
from collections.abc import Callable
from typing import Any

from rich.console import Console

from agent_os.cli.formatter import EventFormatter
from agent_os.cli.parser import format_event

GraphFactory = Callable[[], Any]
InputFunction = Callable[[str], str]


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line contract."""
    parser = argparse.ArgumentParser(
        prog="agent-os",
        description="Run the Agent OS LangGraph workflow.",
    )
    parser.add_argument("task", nargs="?", help="Task description for a new workflow.")
    parser.add_argument("--thread-id", help="Thread ID to create or resume.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted workflow.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show node progress and tracebacks.",
    )
    parser.add_argument("--sandbox", help="Override AGENT_OS_SANDBOX for this run.")
    return parser


def _generate_thread_id() -> str:
    user = os.getenv("USER", "user").strip() or "user"
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{user}-{timestamp}-{uuid.uuid4().hex[:8]}"


def _initial_state(task: str) -> dict[str, object]:
    return {
        "messages": [("user", task)],
        "task": task,
        "plan": None,
        "executor_output": None,
        "human_feedback": None,
        "hot_context": None,
    }


def _pending_interrupt(snapshot: Any) -> object | None:
    for task in getattr(snapshot, "tasks", ()):
        interrupts = getattr(task, "interrupts", ())
        if interrupts:
            return getattr(interrupts[0], "value", interrupts[0])
    return None


def _checkpoint_exists(snapshot: Any) -> bool:
    return bool(
        getattr(snapshot, "created_at", None)
        or getattr(snapshot, "values", None)
    )


def _is_llm_configuration_error(error: ValueError) -> bool:
    message = str(error).lower()
    indicators = (
        "model configured",
        "api_key",
        "api key",
        "api_base",
        "api base",
        "credentials",
    )
    return any(indicator in message for indicator in indicators)


def _print_resume_hint(formatter: EventFormatter, thread_id: str) -> None:
    formatter.print_info(
        f"Checkpoint preserved. Resume with: agent-os --resume --thread-id {thread_id}"
    )


def _read_feedback(
    prompt: object,
    formatter: EventFormatter,
    input_fn: InputFunction,
) -> str:
    from agent_os.nodes.human_gate import normalize_human_feedback

    formatter.print_human_prompt(str(prompt))
    while True:
        raw_feedback = input_fn("> ")
        try:
            return normalize_human_feedback(raw_feedback)
        except ValueError as error:
            formatter.print_error(f"Invalid feedback: {error}")
            formatter.print_info(
                "Enter 'approved', 'y', or 'rejected: <reason>'."
            )


async def _stream_pass(
    graph: Any,
    graph_input: object,
    config: dict[str, object],
    formatter: EventFormatter,
    verbose: bool,
) -> None:
    async for event in graph.astream_events(
        graph_input,
        config=config,
        version="v2",
    ):
        format_event(event, formatter, verbose=verbose)
    formatter.finish_stream()


async def _run_graph(
    graph: Any,
    *,
    task: str | None,
    resume: bool,
    verbose: bool,
    formatter: EventFormatter,
    input_fn: InputFunction,
    thread_id: str,
) -> int:
    from langgraph.types import Command

    from agent_os.routing import build_runtime_config

    config = build_runtime_config(thread_id)

    if resume:
        snapshot = await graph.aget_state(config)
        if not _checkpoint_exists(snapshot):
            formatter.print_error(
                f"Checkpoint not found for thread '{thread_id}'."
            )
            return 2
        if not getattr(snapshot, "next", ()):
            formatter.print_error(
                f"Workflow '{thread_id}' is already finished and cannot be resumed."
            )
            return 2
        interrupt_prompt = _pending_interrupt(snapshot)
        if interrupt_prompt is None:
            formatter.print_error(
                f"Workflow '{thread_id}' is paused without a resumable human gate."
            )
            return 2
        try:
            feedback = _read_feedback(interrupt_prompt, formatter, input_fn)
        except KeyboardInterrupt:
            formatter.print_error("Interrupted by Ctrl+C.")
            _print_resume_hint(formatter, thread_id)
            return 130
        except EOFError:
            formatter.print_error("Input closed while awaiting human feedback.")
            _print_resume_hint(formatter, thread_id)
            return 2
        graph_input: object = Command(resume=feedback)
    else:
        if task is None:
            raise AssertionError("A new workflow requires a task")
        graph_input = _initial_state(task)

    while True:
        try:
            await _stream_pass(
                graph,
                graph_input,
                config,
                formatter,
                verbose,
            )
            snapshot = await graph.aget_state(config)
        except KeyboardInterrupt:
            formatter.print_error("Interrupted by Ctrl+C.")
            _print_resume_hint(formatter, thread_id)
            return 130
        except EOFError:
            formatter.print_error("Input closed while awaiting human feedback.")
            _print_resume_hint(formatter, thread_id)
            return 2
        except ValueError as error:
            if _is_llm_configuration_error(error):
                formatter.print_error("Missing or invalid LLM configuration.")
                formatter.print_info(
                    "Configure LLM_ROUTER, LLM_ARCHITECT, and LLM_EXECUTOR; "
                    "see .env.example."
                )
            else:
                formatter.print_error(f"Workflow error: {error}")
            if verbose:
                traceback.print_exc(file=formatter.console.file)
            return 1
        except Exception as error:
            formatter.print_error(f"Workflow failed: {error}")
            if verbose:
                traceback.print_exc(file=formatter.console.file)
            return 1

        if not getattr(snapshot, "next", ()):
            return 0

        interrupt_prompt = _pending_interrupt(snapshot)
        if interrupt_prompt is None:
            formatter.print_error(
                "Workflow paused at an unsupported node; checkpoint preserved."
            )
            _print_resume_hint(formatter, thread_id)
            return 1

        try:
            feedback = _read_feedback(interrupt_prompt, formatter, input_fn)
        except KeyboardInterrupt:
            formatter.print_error("Interrupted by Ctrl+C.")
            _print_resume_hint(formatter, thread_id)
            return 130
        except EOFError:
            formatter.print_error("Input closed while awaiting human feedback.")
            _print_resume_hint(formatter, thread_id)
            return 2
        graph_input = Command(resume=feedback)


async def async_main(
    argv: list[str] | None = None,
    *,
    graph_factory: GraphFactory | None = None,
    input_fn: InputFunction = input,
    console: Console | None = None,
) -> int:
    """Parse arguments, construct the graph lazily, and run one workflow."""
    args = build_parser().parse_args(argv)
    formatter = EventFormatter(console=console)

    if args.resume and args.task:
        formatter.print_error("Do not provide a task when using --resume.")
        return 2
    if args.resume and not args.thread_id:
        formatter.print_error("--thread-id is required when using --resume.")
        return 2
    if not args.resume and not args.task:
        formatter.print_error("Task is required for a new workflow.")
        return 2

    thread_id = args.thread_id or _generate_thread_id()
    formatter.print_thread_id(thread_id)

    previous_sandbox = os.environ.get("AGENT_OS_SANDBOX")
    if args.sandbox:
        os.environ["AGENT_OS_SANDBOX"] = args.sandbox

    # LiteLLM otherwise performs an HTTP fetch while importing model metadata.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    try:
        if graph_factory is not None:
            graph = graph_factory()
            return await _run_graph(
                graph,
                task=args.task,
                resume=args.resume,
                verbose=args.verbose,
                formatter=formatter,
                input_fn=input_fn,
                thread_id=thread_id,
            )

        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        from agent_os.checkpoints import (
            CHECKPOINT_DB_ENV,
            DEFAULT_CHECKPOINT_DB,
            get_checkpoint_serializer,
        )
        from agent_os.graph import build_graph

        database_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
        async with AsyncSqliteSaver.from_conn_string(database_path) as saver:
            saver.serde = get_checkpoint_serializer()
            graph = build_graph(checkpointer=saver)
            return await _run_graph(
                graph,
                task=args.task,
                resume=args.resume,
                verbose=args.verbose,
                formatter=formatter,
                input_fn=input_fn,
                thread_id=thread_id,
            )
    except KeyboardInterrupt:
        formatter.print_error("Interrupted by Ctrl+C.")
        _print_resume_hint(formatter, thread_id)
        return 130
    except Exception as error:
        formatter.print_error(f"Failed to initialize workflow: {error}")
        if args.verbose:
            traceback.print_exc(file=formatter.console.file)
        return 2
    finally:
        if args.sandbox:
            if previous_sandbox is None:
                os.environ.pop("AGENT_OS_SANDBOX", None)
            else:
                os.environ["AGENT_OS_SANDBOX"] = previous_sandbox


def main(argv: list[str] | None = None) -> int:
    """Synchronous console-script boundary."""
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        print("Interrupted by Ctrl+C.", file=sys.stderr)
        return 130
