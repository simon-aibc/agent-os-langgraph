"""Resolve, compare, and validate persisted backend selections."""

import os
from pathlib import Path

from agent_os.backends import BackendRegistry
from agent_os.sandbox import get_sandbox_root
from agent_os.state import BackendBinding

EFFECTIVE_BINDING_FIELDS = (
    "router",
    "architect",
    "executor",
    "sandbox_root",
)


def resolve_backend_binding(profile_name: str | None) -> BackendBinding:
    """Resolve the current post-profile environment into a durable binding."""
    return BackendBinding(
        router=os.getenv("LLM_ROUTER"),
        architect=os.getenv("LLM_ARCHITECT"),
        executor=os.getenv("LLM_EXECUTOR"),
        profile_name=profile_name,
        sandbox_root=str(get_sandbox_root()),
    )


def binding_conflicts(
    persisted: BackendBinding,
    current: BackendBinding,
) -> dict[str, tuple[str | None, str | None]]:
    """Return effective-value changes, intentionally ignoring profile metadata."""
    changes: dict[str, tuple[str | None, str | None]] = {}
    for field in EFFECTIVE_BINDING_FIELDS:
        old = getattr(persisted, field)
        new = getattr(current, field)
        if old != new:
            changes[field] = (old, new)
    return changes


def validate_backend_binding(
    binding: BackendBinding,
    registry: BackendRegistry,
) -> None:
    """Validate role adapters and the normalized sandbox before forced rebind."""
    for role in ("architect", "executor"):
        configured = getattr(binding, role)
        if configured and configured.startswith("cli/"):
            registry.resolve(role, configured[4:])

    sandbox = Path(binding.sandbox_root)
    if not sandbox.is_absolute():
        raise ValueError("sandbox_root must be an absolute path")
