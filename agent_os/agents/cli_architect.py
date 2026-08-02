import json
import os
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
from agent_os.sandbox import get_sandbox_root
from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState

MAX_INVENTORY_FILES = 1000
_MAX_INVENTORY_DIRECTORIES = 1000


def _build_sandbox_inventory() -> list[str]:
    """
    Build a stable, sorted list of files under the sandbox root.
    Returns relative paths as strings.
    Ignores symlinks pointing outside the sandbox.
    Bounds the listing to MAX_INVENTORY_FILES to prevent unbounded prompts.
    """
    sandbox = get_sandbox_root()
    if not sandbox.exists():
        return []

    valid_files: list[str] = []
    visited_directories = 0

    for root, dirs, files in os.walk(sandbox, followlinks=False):
        if len(valid_files) >= MAX_INVENTORY_FILES:
            break
        visited_directories += 1
        if visited_directories > _MAX_INVENTORY_DIRECTORIES:
            break

        root_path = Path(root)
        safe_dirs: list[str] = []
        for directory in sorted(dirs):
            directory_path = root_path / directory
            try:
                if directory_path.is_symlink():
                    continue
                if directory_path.resolve().is_relative_to(sandbox):
                    safe_dirs.append(directory)
            except (OSError, RuntimeError):
                continue
        dirs[:] = safe_dirs

        for filename in sorted(files):
            if len(valid_files) >= MAX_INVENTORY_FILES:
                break

            file_path = root_path / filename
            try:
                resolved_file = file_path.resolve()
                if resolved_file.is_relative_to(sandbox) and resolved_file.is_file():
                    rel_path = file_path.relative_to(sandbox)
                    valid_files.append(rel_path.as_posix())
            except (OSError, RuntimeError, ValueError):
                continue

    return sorted(valid_files)


def _build_architect_prompt(state: SimonState) -> str:
    """
    Build the prompt text for the CLI architect.
    Includes the original task, sandbox inventory, and any rejection feedback.
    """
    inventory = _build_sandbox_inventory()

    prompt = f"Task:\n{state['task']}\n\n"

    if inventory:
        prompt += "Available files in sandbox:\n"
        for f in inventory:
            prompt += f"- {f}\n"
        prompt += "\n"
    else:
        prompt += "Available files in sandbox: (empty)\n\n"

    feedback = state.get("human_feedback")
    if feedback and feedback.startswith("rejected:"):
        prompt += f"Previous plan was rejected with feedback:\n{feedback}\n\n"

    prompt += "Please analyze the task and return a structured plan matching the ArchitectBrief schema. Do not execute any code directly."

    return prompt


def build_cli_architect_invoker(
    backend: str,
) -> Callable[[SimonState], ArchitectBrief]:
    """
    Returns a callable that executes the CLI architect node logic for a specific backend.
    Supported backends: 'claude-code', 'codex'.
    """

    if backend not in ("claude-code", "codex"):
        raise ValueError(
            f"Unsupported CLI architect backend: {backend}. "
            "Must be 'claude-code' or 'codex'."
        )

    def invoker(state: SimonState) -> ArchitectBrief:
        prompt = _build_architect_prompt(state)

        if backend == "claude-code":
            schema_str = json.dumps(ArchitectBrief.model_json_schema())
            args = [
                "-p",
                prompt,
                "--permission-mode",
                "plan",
                "--output-format",
                "stream-json",
                "--verbose",
                "--json-schema",
                schema_str,
            ]
            result = run_cli_command("claude", args)
            parsed_json = parse_claude_stream_json(result.stdout)

        else:
            with tempfile.TemporaryDirectory(prefix="agent-os-codex-") as temp_dir:
                temp_output = Path(temp_dir) / "last-message.json"
                with write_schema_file(ArchitectBrief) as schema_path:
                    args = [
                        "exec",
                        "--sandbox",
                        "read-only",
                        "--output-schema",
                        str(schema_path),
                        "--output-last-message",
                        str(temp_output),
                        prompt,
                    ]
                    run_cli_command("codex", args)
                parsed_json = parse_codex_output_file(temp_output)

        try:
            return ArchitectBrief.model_validate(parsed_json)
        except ValidationError as exc:
            raise ValueError(
                f"Failed to validate {backend} structured output as ArchitectBrief. "
                "The payload did not match the required schema."
            ) from exc

    return invoker
