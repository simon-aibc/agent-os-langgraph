"""Workspace loading and runtime composition."""

import os
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from agent_os.backends import BackendRegistry, build_default_registry
from agent_os.bindings import resolve_backend_binding
from agent_os.connectors import (
    ConnectorRegistry,
    FilesystemConnector,
    GbrainConnector,
    MarkdownVaultConnector,
    MemoryConnector,
)
from agent_os.default_registry import build_default_registry as build_skill_registry
from agent_os.hot_context import load_hot_context
from agent_os.policy import LocalPolicy
from agent_os.skill_packages import SkillPackageLoader
from agent_os.skills import SkillRegistry
from agent_os.state import BackendBinding


class WorkspaceLoadError(ValueError):
    """Raised for invalid, unsafe, or unresolvable workspace configuration."""


class WorkspaceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    department: str | None = None
    organization: str | None = None


class Workspace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceMeta
    backends: dict[str, str | None] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    memory: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)

    _base_path: Path = PrivateAttr(default_factory=lambda: Path.cwd().resolve())

    @property
    def base_path(self) -> Path:
        return self._base_path


@dataclass(frozen=True)
class ComposedWorkspace:
    workspace: Workspace
    backend_binding: BackendBinding
    backend_registry: BackendRegistry
    skill_registry: SkillRegistry
    connector_registry: ConnectorRegistry
    memory_connector: MemoryConnector
    policy: LocalPolicy
    hot_context: str
    limits: dict[str, Any]
    environment: dict[str, str | None]


_BACKEND_ROLES = frozenset({"router", "architect", "executor"})
_PATH_KEYS = frozenset({"path", "root", "root_path", "vault_path"})
_RESTRICTED_FILENAMES = frozenset({"db_config.php", "mail_config.php", ".env"})


def load_workspace(path: str | Path) -> Workspace:
    """Load and validate a workspace TOML file."""

    workspace_path = _resolve_workspace_path(path)
    _reject_restricted_path(workspace_path)

    try:
        with workspace_path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise WorkspaceLoadError(
            f"Malformed TOML in workspace file '{workspace_path}': {exc}"
        ) from exc
    except OSError as exc:
        raise WorkspaceLoadError(
            f"Unable to read workspace file '{workspace_path}': {exc}"
        ) from exc

    try:
        workspace = Workspace.model_validate(data)
    except Exception as exc:
        raise WorkspaceLoadError(
            f"Invalid workspace configuration in '{workspace_path}': {exc}"
        ) from exc

    workspace._base_path = workspace_path.parent
    workspace = _resolve_workspace_paths(workspace)
    _validate_backend_bindings(workspace, build_default_registry())
    _build_workspace_skill_registry(workspace)
    connector_registry, _ = _build_connector_registry(workspace)
    _validate_connector_references(workspace, connector_registry)
    return workspace


def compose_workspace(ws: Workspace) -> ComposedWorkspace:
    """Compose a workspace into isolated runtime registries and bindings."""

    backend_registry = build_default_registry()
    _validate_backend_bindings(ws, backend_registry)
    skill_registry = _build_workspace_skill_registry(ws)
    connector_registry, memory_connector = _build_connector_registry(ws)
    _validate_connector_references(ws, connector_registry)

    environment = _workspace_environment(ws)
    with _patched_environment(environment):
        backend_binding = resolve_backend_binding(f"workspace:{ws.workspace.name}")

    context_config = ws.context
    sources = _optional_string_list(context_config.get("sources"), "context.sources")
    hot_context = load_hot_context(
        memory_connector,
        max_chars=int(context_config.get("max_chars", 8000)),
        max_age_days=int(context_config.get("max_age_days", 14)),
        sources=sources,
    )

    return ComposedWorkspace(
        workspace=ws,
        backend_binding=backend_binding,
        backend_registry=backend_registry,
        skill_registry=skill_registry,
        connector_registry=connector_registry,
        memory_connector=memory_connector,
        policy=LocalPolicy(dict(ws.policy)),
        hot_context=hot_context,
        limits=dict(ws.limits),
        environment=environment,
    )


def _resolve_workspace_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_dir():
        candidate = candidate / "workspace.toml"
    return candidate.resolve()


def _reject_restricted_path(path: Path) -> None:
    name = path.name.lower()
    if (
        name in _RESTRICTED_FILENAMES
        or "credentials" in name
        or "token" in name
        or name.startswith("auth")
    ):
        raise WorkspaceLoadError(f"Refusing to load restricted configuration path: {path}")


def _resolve_workspace_paths(ws: Workspace) -> Workspace:
    memory = dict(ws.memory)
    for key in _PATH_KEYS:
        value = memory.get(key)
        if isinstance(value, str) and value.strip():
            memory[key] = _resolve_relative_path(ws.base_path, value)

    resolved_skills = []
    for skill in ws.skills:
        candidate = Path(skill).expanduser()
        if not candidate.is_absolute():
            candidate = ws.base_path / candidate
        resolved_skills.append(str(candidate.resolve()) if candidate.exists() else skill)

    return ws.model_copy(update={"memory": memory, "skills": resolved_skills})


def _resolve_relative_path(base_path: Path, value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_path / path
    return str(path.resolve())


def _validate_backend_bindings(
    ws: Workspace,
    registry: BackendRegistry,
) -> None:
    for role, value in ws.backends.items():
        if role not in _BACKEND_ROLES:
            expected = ", ".join(sorted(_BACKEND_ROLES))
            raise WorkspaceLoadError(
                f"Unknown backend role '{role}' in workspace '{ws.workspace.name}'. "
                f"Expected one of: {expected}."
            )
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise WorkspaceLoadError(
                f"Backend value for role '{role}' must be a non-empty string."
            )
        backend_value = value.strip()
        if role == "router":
            if backend_value.startswith("cli/"):
                raise WorkspaceLoadError(f"Router cannot be a CLI backend: {backend_value}")
            continue
        backend_name = backend_value[4:] if backend_value.startswith("cli/") else backend_value
        try:
            registry.resolve(role, backend_name)
        except ValueError as exc:
            raise WorkspaceLoadError(
                f"Workspace backend '{role}' is not resolvable: {exc}"
            ) from exc


def _build_workspace_skill_registry(ws: Workspace) -> SkillRegistry:
    registry = build_skill_registry()
    loader = SkillPackageLoader(registry)

    for entry in ws.skills:
        if registry.get(entry) is not None:
            continue

        path = Path(entry).expanduser()
        if path.exists():
            before = set(registry.names())
            try:
                if path.is_dir() and (path / "manifest.toml").exists():
                    loader.load_package(path)
                elif path.is_dir():
                    loader.load_from_directories([str(path)])
                else:
                    raise WorkspaceLoadError(f"Skill path '{entry}' is not a directory.")
            except Exception as exc:
                if isinstance(exc, WorkspaceLoadError):
                    raise
                raise WorkspaceLoadError(
                    f"Workspace skill '{entry}' is not resolvable: {exc}"
                ) from exc
            if set(registry.names()) == before:
                raise WorkspaceLoadError(
                    f"Workspace skill path '{entry}' did not register any skills."
                )
            continue

        if _looks_like_path(entry):
            raise WorkspaceLoadError(f"Workspace skill path '{entry}' does not exist.")

        available = ", ".join(registry.names()) or "none"
        raise WorkspaceLoadError(
            f"Unknown workspace skill '{entry}'. Available skills: {available}."
        )

    return registry


def _build_connector_registry(ws: Workspace) -> tuple[ConnectorRegistry, MemoryConnector]:
    registry = ConnectorRegistry()
    registry.register("filesystem", FilesystemConnector())

    memory_connector = _build_memory_connector(ws)
    registry.register("memory", memory_connector)
    registry.register(memory_connector.name, memory_connector)
    if memory_connector.name == "markdown_vault":
        registry.register("markdown", memory_connector)

    return registry, memory_connector


def _build_memory_connector(ws: Workspace) -> MemoryConnector:
    memory_type = str(
        ws.memory.get("type", ws.memory.get("connector", "markdown"))
    ).strip().lower()
    if memory_type in ("markdown", "markdown_vault"):
        root = ws.memory.get("path", ws.memory.get("root_path", ws.memory.get("root", ".")))
        root_path = _resolve_relative_path(ws.base_path, str(root))
        return MarkdownVaultConnector(root_path)
    if memory_type == "gbrain":
        return GbrainConnector()
    raise WorkspaceLoadError(
        f"Unknown memory connector '{memory_type}'. Expected markdown or gbrain."
    )


def _validate_connector_references(
    ws: Workspace,
    registry: ConnectorRegistry,
) -> None:
    for connector in ws.connectors:
        try:
            registry.resolve(connector)
        except ValueError as exc:
            available = ", ".join(registry.list_connectors()) or "none"
            raise WorkspaceLoadError(
                f"Unknown workspace connector '{connector}'. Available connectors: {available}."
            ) from exc


def _workspace_environment(ws: Workspace) -> dict[str, str | None]:
    env: dict[str, str | None] = {}
    role_to_env = {
        "router": "LLM_ROUTER",
        "architect": "LLM_ARCHITECT",
        "executor": "LLM_EXECUTOR",
    }
    for role, env_name in role_to_env.items():
        if role not in ws.backends:
            continue
        value = ws.backends[role]
        if value is None:
            env[env_name] = None
            continue
        normalized = value.strip()
        if role in ("architect", "executor") and not normalized.startswith("cli/"):
            normalized = f"cli/{normalized}"
        env[env_name] = normalized

    memory_type = str(
        ws.memory.get("type", ws.memory.get("connector", "markdown"))
    ).strip().lower()
    if memory_type in ("markdown", "markdown_vault"):
        root = ws.memory.get("path", ws.memory.get("root_path", ws.memory.get("root", ".")))
        env["AGENT_OS_MEMORY_CONNECTOR"] = "markdown"
        env["AGENT_OS_VAULT_PATH"] = _resolve_relative_path(ws.base_path, str(root))
    elif memory_type == "gbrain":
        env["AGENT_OS_MEMORY_CONNECTOR"] = "gbrain"

    return env


@contextmanager
def _patched_environment(values: dict[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _optional_string_list(value: Any, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise WorkspaceLoadError(f"{field_name} must be a list of strings.")
    return value


def _looks_like_path(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or value.startswith(".")
        or value.endswith(".toml")
    )
