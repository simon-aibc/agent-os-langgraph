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
from agent_os.state import BackendBinding

GraphFactory = Callable[[], Any]
InputFunction = Callable[[str], str]


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line contract."""
    parser = argparse.ArgumentParser(
        prog="agent-os",
        description="Run the Agent OS LangGraph workflow.",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser(
        "run",
        help="Run a workflow.",
        description="Run the Agent OS LangGraph workflow.",
    )
    run_parser.add_argument("task", nargs="?", help="Task description for a new workflow.")
    run_parser.add_argument("--thread-id", help="Thread ID to create or resume.")
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted workflow.",
    )
    run_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show node progress and tracebacks.",
    )
    run_parser.add_argument("--sandbox", help="Override AGENT_OS_SANDBOX for this run.")
    run_parser.add_argument("--profile", help="Named configuration profile to use.")
    run_parser.add_argument(
        "--force-rebind",
        action="store_true",
        help="Replace a persisted backend binding when resuming.",
    )

    p_chat = subparsers.add_parser("chat", help="Start an interactive conversational loop")
    p_chat.add_argument("--thread-id", help="Thread ID to persist checkpoint state. Generated if absent.")
    p_chat.add_argument("--resume", action="store_true", help="Resume from the last checkpoint.")
    p_chat.add_argument("-v", "--verbose", action="store_true", help="Show node progress.")
    p_chat.add_argument("--sandbox", help="Override AGENT_OS_SANDBOX for this run.")
    p_chat.add_argument("--profile", help="Named configuration profile to use.")
    p_chat.add_argument("--force-rebind", action="store_true", help="Replace a persisted backend binding when resuming.")

    p_sessions = subparsers.add_parser("sessions", help="Manage chat sessions")
    s_sub = p_sessions.add_subparsers(dest="session_command")
    s_sub.add_parser("list", help="List all sessions")
    
    s_inspect = s_sub.add_parser("inspect", help="Inspect a session")
    s_inspect.add_argument("thread_id", help="Thread ID")
    
    s_delete = s_sub.add_parser("delete", help="Delete a session")
    s_delete.add_argument("thread_id", help="Thread ID")
    
    s_resume = s_sub.add_parser("resume", help="Resume a session")
    s_resume.add_argument("thread_id", help="Thread ID")

    doctor_parser = subparsers.add_parser("doctor", help="Check configuration and health.")
    doctor_parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON.")
    return parser


def _generate_thread_id() -> str:
    user = os.getenv("USER", "user").strip() or "user"
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{user}-{timestamp}-{uuid.uuid4().hex[:8]}"


def _initial_state(
    task: str,
    backend_binding: BackendBinding,
) -> dict[str, object]:
    return {
        "messages": [("user", task)],
        "task": task,
        "plan": None,
        "executor_output": None,
        "human_feedback": None,
        "hot_context": None,
        "conversation_summary": None,
        "backend_binding": backend_binding,
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


def _next_node_name(snapshot: Any) -> str:
    next_nodes = tuple(getattr(snapshot, "next", ()) or ())
    return str(next_nodes[0]) if next_nodes else "unknown"


def _render_binding(binding: BackendBinding) -> str:
    return ", ".join(
        (
            f"router={binding.router!r}",
            f"architect={binding.architect!r}",
            f"executor={binding.executor!r}",
            f"profile_name={binding.profile_name!r}",
            f"sandbox_root={binding.sandbox_root!r}",
        )
    )


async def _prepare_resume_binding(
    graph: Any,
    config: dict[str, object],
    snapshot: Any,
    current: BackendBinding,
    force_rebind: bool,
    registry: Any,
    formatter: EventFormatter,
) -> tuple[Any | None, int | None]:
    from agent_os.bindings import binding_conflicts, validate_backend_binding

    values = getattr(snapshot, "values", None) or {}
    raw_persisted = values.get("backend_binding") if isinstance(values, dict) else None
    resume_node = _next_node_name(snapshot)

    if raw_persisted is None:
        if not force_rebind:
            formatter.print_error(
                "This checkpoint has no persisted backend binding (created before "
                "R1.2e). Resuming without an explicit backend selection is not "
                "safe. Pass --force-rebind to attach the current binding and "
                "continue. Prior backend selection is not inferred."
            )
            return None, 2
        try:
            validate_backend_binding(current, registry)
        except ValueError as error:
            formatter.print_error(f"Cannot force backend rebind: {error}")
            return None, 2
        formatter.print_warning(
            "Attaching current backend binding to a legacy checkpoint (no prior "
            f"binding present). New binding: {_render_binding(current)}. Current "
            f"resume node: {resume_node}."
        )
    else:
        try:
            persisted = BackendBinding.model_validate(raw_persisted)
        except ValueError as error:
            formatter.print_error(f"Persisted backend binding is invalid: {error}")
            return None, 2
        changes = binding_conflicts(persisted, current)
        if not changes:
            return snapshot, None
        if not force_rebind:
            rendered_changes = "; ".join(
                f"{field}: {old!r} -> {new!r}"
                for field, (old, new) in changes.items()
            )
            formatter.print_error(
                "Backend binding conflict. Persisted binding: "
                f"{_render_binding(persisted)}. Conflicting effective overrides: "
                f"{rendered_changes}. Edit the environment or profile to match, "
                "or pass --force-rebind."
            )
            return None, 2
        try:
            validate_backend_binding(current, registry)
        except ValueError as error:
            formatter.print_error(f"Cannot force backend rebind: {error}")
            return None, 2
        formatter.print_warning("Forcing backend rebind:")
        for field, (old, new) in changes.items():
            formatter.print_warning(f"{field}: {old!r} -> {new!r}")
        formatter.print_warning(f"Current resume node: {resume_node}")

    if resume_node == "executor":
        formatter.print_warning(
            "Partial edits may exist in the sandbox. Inspect before continuing."
        )
    await graph.aupdate_state(config, {"backend_binding": current})
    return await graph.aget_state(config), None


def _completed_with_tool_failure(snapshot: Any) -> bool:
    values = getattr(snapshot, "values", None) or {}
    if not isinstance(values, dict):
        return False
    tool_result = values.get("tool_result")
    return getattr(tool_result, "success", None) is False


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
    backend_binding: BackendBinding,
    force_rebind: bool,
    registry: Any,
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
        snapshot, binding_exit = await _prepare_resume_binding(
            graph,
            config,
            snapshot,
            backend_binding,
            force_rebind,
            registry,
            formatter,
        )
        if binding_exit is not None:
            return binding_exit
        assert snapshot is not None
        interrupt_prompt = _pending_interrupt(snapshot)
        if interrupt_prompt is not None:
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
            formatter.print_info(f"Resuming mid-run at node {_next_node_name(snapshot)}")
            graph_input = None
    else:
        if task is None:
            raise AssertionError("A new workflow requires a task")
        graph_input = _initial_state(task, backend_binding)

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
            if _completed_with_tool_failure(snapshot):
                return 1
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

async def _chat_loop(
    graph: Any,
    *,
    resume: bool,
    verbose: bool,
    formatter: EventFormatter,
    input_fn: InputFunction,
    thread_id: str,
    backend_binding: BackendBinding,
    force_rebind: bool,
    registry: Any,
) -> int:
    from langchain_core.messages import HumanMessage
    from langgraph.types import Command

    from agent_os.routing import build_runtime_config

    config = build_runtime_config(thread_id)

    if resume:
        snapshot = await graph.aget_state(config)
        if not _checkpoint_exists(snapshot):
            formatter.print_error(f"Checkpoint not found for thread '{thread_id}'.")
            return 2
        snapshot, binding_exit = await _prepare_resume_binding(
            graph, config, snapshot, backend_binding, force_rebind, registry, formatter
        )
        if binding_exit is not None:
            return binding_exit
        assert snapshot is not None
        
        interrupt_prompt = _pending_interrupt(snapshot)
        if interrupt_prompt is not None:
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
            try:
                await _stream_pass(graph, graph_input, config, formatter, verbose)
            except KeyboardInterrupt:
                formatter.print_error("Interrupted by Ctrl+C.")
                _print_resume_hint(formatter, thread_id)
                return 130
            except EOFError:
                formatter.print_error("Input closed.")
                _print_resume_hint(formatter, thread_id)
                return 2
            except Exception as error:
                formatter.print_error(f"Workflow failed: {error}")
                if verbose:
                    traceback.print_exc(file=formatter.console.file)
                return 1

    while True:
        try:
            user_input = input_fn("> ")
            if user_input.strip() in ("/exit", "exit"):
                break
        except KeyboardInterrupt:
            formatter.print_error("Interrupted by Ctrl+C.")
            _print_resume_hint(formatter, thread_id)
            return 130
        except EOFError:
            break
            
        snapshot = await graph.aget_state(config)
        
        if not _checkpoint_exists(snapshot):
            # First turn: initialize state with the first message as task
            graph_input = _initial_state(user_input, backend_binding)
        else:
            graph_input = {"messages": [HumanMessage(content=user_input)]}
            
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
                if _completed_with_tool_failure(snapshot):
                    return 1
                break

            interrupt_prompt = _pending_interrupt(snapshot)
            if interrupt_prompt is None:
                formatter.print_error("Workflow paused at an unsupported node; checkpoint preserved.")
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

        from agent_os.sessions import upsert_session
        title = None
        if not _checkpoint_exists(snapshot) and isinstance(graph_input, dict) and "messages" in graph_input:
            msg = graph_input["messages"][0]
            content = msg[1] if isinstance(msg, tuple) else msg.content
            title = content[:50] + ("..." if len(content) > 50 else "")
        upsert_session(thread_id, title)
            
    # On exit, write session log if summary exists
    try:
        final_snapshot = await graph.aget_state(config)
        summary = final_snapshot.values.get("conversation_summary")
        if summary:
            import os

            from agent_os.connectors import GbrainConnector, MarkdownVaultConnector
            from agent_os.session_log import write_session_summary
            from agent_os.sessions import _get_db
            
            connector_name = os.getenv("AGENT_OS_MEMORY_CONNECTOR", "markdown")
            if connector_name == "gbrain":
                connector = GbrainConnector()
            else:
                vault_path = os.getenv("AGENT_OS_VAULT_PATH", backend_binding.sandbox_root)
                connector = MarkdownVaultConnector(vault_path)
                
            with _get_db() as db:
                c = db.execute("SELECT turn_count, created_at, title FROM sessions WHERE thread_id = ?", (thread_id,))
                row = c.fetchone()
                
            session_meta = {
                "turn_count": row[0] if row else 0,
                "created_at": row[1] if row else "",
                "title": row[2] if row else "Untitled Session"
            }
            write_session_summary(connector, thread_id, summary, session_meta)
    except Exception as e:
        formatter.print_warning(f"Failed to write session log: {e}")

    return 0


async def async_main(
    argv: list[str] | None = None,
    *,
    graph_factory: GraphFactory | None = None,
    input_fn: InputFunction = input,
    console: Console | None = None,
) -> int:
    """Parse arguments, construct the graph lazily, and run one workflow."""
    if argv is None:
        argv = sys.argv[1:]

    # Normalize argv: if first meaningful token isn't "run", "doctor", "chat", or "sessions", prepend "run"
    # This also routes naked -h/--help to 'run --help' to preserve legacy help visibility.
    if not argv or argv[0] not in ("run", "doctor", "chat", "sessions"):
        argv = ["run"] + argv

    args = build_parser().parse_args(argv)

    if args.command == "sessions":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB
        from agent_os.sessions import delete_session, get_session, list_sessions
        
        formatter = EventFormatter(console=console)
        if args.session_command == "list":
            sessions = list_sessions()
            for s in sessions:
                formatter.print_info(f"ID: {s['thread_id']} | Turns: {s['turn_count']} | Last: {s['last_turn_at'][:16]} | {s['title']}")
            return 0
        elif args.session_command == "resume":
            # Delegate to chat
            args.command = "chat"
            args.resume = True
            args.thread_id = args.thread_id
            args.task = None
            args.verbose = False
            args.sandbox = None
            args.profile = None
            args.force_rebind = False
        elif args.session_command == "inspect":
            session = get_session(args.thread_id)
            if not session:
                formatter.print_error(f"Session {args.thread_id} not found in index.")
                return 1
            formatter.print_info(f"Session: {args.thread_id}")
            formatter.print_info(f"Title: {session['title']}")
            formatter.print_info(f"Turns: {session['turn_count']}")
            return 0
        elif args.session_command == "delete":
            session = get_session(args.thread_id)
            if not session:
                formatter.print_error(f"Session {args.thread_id} not found.")
                return 1
            formatter.print_human_prompt(f"Are you sure you want to delete session '{args.thread_id}'? This will permanently delete the checkpoint. (y/N)")
            ans = input_fn("> ")
            if ans.lower() in ("y", "yes"):
                database_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
                async with AsyncSqliteSaver.from_conn_string(database_path) as saver:
                    await saver.adelete_thread(args.thread_id)
                delete_session(args.thread_id)
                formatter.print_info(f"Session {args.thread_id} deleted.")
                return 0
            else:
                formatter.print_info("Deletion cancelled.")
                return 0

    if args.command == "doctor":
        from agent_os.cli.doctor import run_doctor
        exit_code, output = run_doctor(args.json_output)
        print(output)
        return exit_code

    formatter = EventFormatter(console=console)

    if args.command == "run":
        if args.resume and args.task:
            formatter.print_error("Do not provide a task when using --resume.")
            return 2
        if not args.resume and not args.task:
            formatter.print_error("Task is required for a new workflow.")
            return 2
    if args.resume and not args.thread_id:
        formatter.print_error("--thread-id is required when using --resume.")
        return 2
    if args.force_rebind and not args.resume:
        formatter.print_error("--force-rebind flag requires --resume.")
        return 2

    thread_id = args.thread_id or _generate_thread_id()
    formatter.print_thread_id(thread_id)

    # Resolve profile
    from agent_os.backends import build_default_registry
    from agent_os.profiles import load_profiles, resolve_profile, select_profile_name
    from agent_os.sandbox import get_sandbox_root

    try:
        profile_file = load_profiles()
        cli_name = args.profile
        env_name = os.getenv("AGENT_OS_PROFILE")
        file_default = profile_file.default

        profile_name, _ = select_profile_name(cli_name, env_name, file_default)
        resolved_prof = None
        registry = build_default_registry()
        if profile_name is not None:
            resolved_prof = resolve_profile(
                profile_file,
                profile_name,
                registry,
                get_sandbox_root().resolve()
            )
    except Exception as e:
        formatter.print_error(f"Profile error: {e}")
        return 2

    previous_env = {
        "LLM_ROUTER": os.environ.get("LLM_ROUTER"),
        "LLM_ARCHITECT": os.environ.get("LLM_ARCHITECT"),
        "LLM_EXECUTOR": os.environ.get("LLM_EXECUTOR"),
        "AGENT_OS_SANDBOX": os.environ.get("AGENT_OS_SANDBOX"),
    }

    if resolved_prof is not None:
        profile_env = {
            "LLM_ROUTER": resolved_prof.router,
            "LLM_ARCHITECT": resolved_prof.architect,
            "LLM_EXECUTOR": resolved_prof.executor,
            "AGENT_OS_SANDBOX": resolved_prof.sandbox,
        }
        for key, value in profile_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if args.sandbox:
        os.environ["AGENT_OS_SANDBOX"] = args.sandbox

    # LiteLLM otherwise performs an HTTP fetch while importing model metadata.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    try:
        from agent_os.bindings import resolve_backend_binding

        backend_binding = resolve_backend_binding(profile_name)
        if graph_factory is not None:
            graph = graph_factory()
            if args.command == "chat":
                return await _chat_loop(
                    graph,
                    resume=args.resume,
                    verbose=args.verbose,
                    formatter=formatter,
                    input_fn=input_fn,
                    thread_id=thread_id,
                    backend_binding=backend_binding,
                    force_rebind=args.force_rebind,
                    registry=registry,
                )
            else:
                return await _run_graph(
                    graph,
                    task=args.task,
                    resume=args.resume,
                    verbose=args.verbose,
                    formatter=formatter,
                    input_fn=input_fn,
                    thread_id=thread_id,
                    backend_binding=backend_binding,
                    force_rebind=args.force_rebind,
                    registry=registry,
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
            if args.command == "chat":
                return await _chat_loop(
                    graph,
                    resume=args.resume,
                    verbose=args.verbose,
                    formatter=formatter,
                    input_fn=input_fn,
                    thread_id=thread_id,
                    backend_binding=backend_binding,
                    force_rebind=args.force_rebind,
                    registry=registry,
                )
            else:
                return await _run_graph(
                    graph,
                    task=args.task,
                    resume=args.resume,
                    verbose=args.verbose,
                    formatter=formatter,
                    input_fn=input_fn,
                    thread_id=thread_id,
                    backend_binding=backend_binding,
                    force_rebind=args.force_rebind,
                    registry=registry,
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
        for k, v in previous_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main(argv: list[str] | None = None) -> int:
    """Synchronous console-script boundary."""
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        print("Interrupted by Ctrl+C.", file=sys.stderr)
        return 130
