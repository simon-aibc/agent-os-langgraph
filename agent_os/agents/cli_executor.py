import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from agent_os.cli_backends import (
    parse_claude_stream_json,
    parse_codex_output_file,
    run_cli_command,
    write_schema_file,
)
from agent_os.schemas import ArchitectBrief, ExecutorReport
from agent_os.state import SimonState


def build_executor_prompt(plan: ArchitectBrief) -> str:
    """Build the prompt for the executor CLI."""
    prompt = (
        "You are an executor agent. Apply the following approved architectural "
        "plan inside the current sandbox directory. Do NOT access or modify any "
        "files outside the current working directory.\n\n"
        "Approved Plan:\n"
        f"{plan.model_dump_json(indent=2)}\n\n"
    )

    if plan.verify_cmd:
        prompt += (
            f"After making the changes, you MUST run the following verification command:\n"
            f"`{plan.verify_cmd}`\n\n"
        )
    else:
        prompt += "No verification command was provided.\n\n"

    prompt += (
        "Return an ExecutorReport with your results. "
        "Set success to true only if all changes were applied and the verification passed."
    )

    return prompt


def build_cli_executor_invoker(backend: str) -> Callable[[SimonState], ExecutorReport]:
    """
    Returns a callable that executes the CLI executor node logic for a specific backend.
    Supported backends: 'claude-code', 'codex'.
    """
    if backend not in ("claude-code", "codex"):
        raise ValueError(
            f"Unsupported CLI executor backend: {backend}. "
            "Must be 'claude-code' or 'codex'."
        )

    def invoker(state: SimonState) -> ExecutorReport:
        plan = state.get("plan")
        if not isinstance(plan, ArchitectBrief):
            raise ValueError("State 'plan' must be an ArchitectBrief instance.")

        prompt = build_executor_prompt(plan)

        if backend == "claude-code":
            schema_str = json.dumps(ExecutorReport.model_json_schema())
            args = [
                "-p",
                prompt,
                "--permission-mode",
                "acceptEdits",
                "--output-format",
                "stream-json",
                "--verbose",
                "--json-schema",
                schema_str,
            ]
            result = run_cli_command("claude", args)
            parsed = parse_claude_stream_json(result.stdout)

        else:
            with tempfile.TemporaryDirectory(prefix="agent-os-codex-") as temp_dir:
                out_path = Path(temp_dir) / "last-message.json"
                with write_schema_file(ExecutorReport, strict=True) as schema_path:
                    args = [
                        "exec",
                        "--sandbox",
                        "workspace-write",
                        "--output-schema",
                        str(schema_path),
                        "--output-last-message",
                        str(out_path),
                        prompt,
                    ]
                    run_cli_command("codex", args)
                parsed = parse_codex_output_file(out_path)

        try:
            return ExecutorReport.model_validate(parsed)
        except ValidationError as exc:
            raise ValueError(
                f"Failed to validate {backend} structured output as ExecutorReport. "
                "The payload did not match the required schema."
            ) from exc

    return invoker
