"""Backend adapter contracts and registry for role-based provider resolution."""

from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel

from agent_os.schemas import ArchitectBrief, ExecutorReport
from agent_os.state import SimonState

BackendRole = Literal["architect", "executor"]
BackendArtifact = ArchitectBrief | ExecutorReport
BackendInvoker = Callable[[SimonState], BackendArtifact]


class AuthStatus(BaseModel):
    """Safe, structured authentication status for an adapter."""

    status: Literal["ok", "unauthenticated", "unknown"]
    detail: str = ""


class BackendAdapter(Protocol):
    """Contract implemented by providers that can serve graph roles."""

    name: str
    binary_name: str
    supported_roles: frozenset[BackendRole]

    def build_invoker(self, role: BackendRole) -> BackendInvoker: ...

    def authentication_status(self) -> AuthStatus: ...


class BackendRegistry:
    """Resolve registered adapters by normalized backend name and role."""

    def __init__(self) -> None:
        self._adapters: dict[str, BackendAdapter] = {}

    @property
    def names(self) -> tuple[str, ...]:
        """Return registered names in stable order for diagnostics."""

        return tuple(sorted(self._adapters))

    def register(self, adapter: BackendAdapter) -> None:
        """Register an adapter, rejecting backend-name collisions."""

        name = adapter.name.strip()
        if not name:
            raise ValueError("Backend adapter name must not be empty.")
        if name in self._adapters:
            raise ValueError(f"Backend adapter name already registered: {name}")
        self._adapters[name] = adapter

    def resolve(self, role: BackendRole, name: str) -> BackendAdapter:
        """Resolve an adapter and verify that it supports the requested role."""

        adapter = self._adapters.get(name)
        if adapter is None:
            registered = ", ".join(self.names) or "(none)"
            raise ValueError(
                f"Unknown backend adapter '{name}'. Registered adapters: {registered}"
            )
        if role not in adapter.supported_roles:
            supported = ", ".join(sorted(adapter.supported_roles)) or "none"
            raise ValueError(
                f"Backend adapter '{name}' does not support role '{role}'. "
                f"Supported roles: {supported}"
            )
        return adapter
