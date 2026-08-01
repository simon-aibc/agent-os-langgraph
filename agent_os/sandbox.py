import os
from pathlib import Path


def get_sandbox_root() -> Path:
    """
    Read AGENT_OS_SANDBOX on every call.
    Default is './sandbox'.
    Relative values resolve from Path.cwd().
    Returns a resolved absolute Path.
    """
    sandbox_env = os.getenv("AGENT_OS_SANDBOX", "./sandbox")
    return Path(sandbox_env).resolve()


def get_read_root() -> Path:
    """Use an explicit sandbox for reads, otherwise preserve cwd behavior."""
    configured_root = os.getenv("AGENT_OS_SANDBOX")
    if configured_root:
        return Path(configured_root).resolve()
    return Path.cwd().resolve()


def resolve_sandbox_path(path: str) -> Path:
    """
    Resolves a user path and rejects anything outside the sandbox,
    including traversal and symlink escapes.
    Does not create directories or mutate the filesystem.
    """
    sandbox_root = get_sandbox_root()
    target_path = Path(path)

    if not target_path.is_absolute():
        target_path = sandbox_root / target_path

    resolved_path = target_path.resolve()

    if not resolved_path.is_relative_to(sandbox_root):
        raise ValueError(f"Path {path} resolves outside the sandbox")

    return resolved_path
