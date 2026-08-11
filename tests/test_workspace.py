import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from agent_os.cli.app import async_main
from agent_os.workspace import WorkspaceLoadError, compose_workspace, load_workspace


def _write_workspace(
    root: Path,
    *,
    name: str = "demo",
    architect: str = "codex",
    executor: str = "codex",
    department: str | None = "Operations",
    organization: str | None = "ExampleCo",
    skills: list[str] | None = None,
    connectors: list[str] | None = None,
    policy_mode: str = "local",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SYSTEM.md").write_text("# System\nUse the workspace context.\n")
    (root / "CONTEXT.md").write_text("# Context\nSeeded public example context.\n")
    skills = skills or []
    connectors = connectors or ["filesystem", "memory"]
    department_line = f'department = "{department}"\n' if department is not None else ""
    organization_line = (
        f'organization = "{organization}"\n' if organization is not None else ""
    )
    workspace_path = root / "workspace.toml"
    workspace_path.write_text(
        "\n".join(
            [
                f"skills = {skills!r}",
                f"connectors = {connectors!r}",
                "",
                "[workspace]",
                f'name = "{name}"',
                department_line.rstrip(),
                organization_line.rstrip(),
                "",
                "[backends]",
                f'architect = "{architect}"',
                f'executor = "{executor}"',
                "",
                "[memory]",
                'type = "markdown"',
                'path = "."',
                "",
                "[context]",
                'sources = ["SYSTEM.md", "CONTEXT.md"]',
                "max_chars = 4000",
                "max_age_days = 3650",
                "",
                "[policy]",
                f'mode = "{policy_mode}"',
                "",
                "[limits]",
                "recursion_limit = 7",
                "",
            ]
        )
    )
    return workspace_path


def _write_skill_package(root: Path) -> Path:
    package = root / "skills" / "hello_skill"
    package.mkdir(parents=True)
    (package / "manifest.toml").write_text(
        "\n".join(
            [
                "[skill]",
                'name = "hello_skill"',
                'version = "0.1.0"',
                "",
                "[[skill.handlers]]",
                'match = ["hello_skill", "hello"]',
                'entrypoint = "handlers:hello_skill"',
                "",
            ]
        )
    )
    (package / "handlers.py").write_text(
        "def hello_skill(task: str = '', **kwargs):\n"
        "    return {'task': task, 'ok': True}\n"
    )
    return package


def test_load_valid_workspace(tmp_path):
    workspace_path = _write_workspace(tmp_path)

    workspace = load_workspace(workspace_path)

    assert workspace.workspace.name == "demo"
    assert workspace.workspace.department == "Operations"
    assert workspace.workspace.organization == "ExampleCo"
    assert workspace.memory["path"] == str(tmp_path.resolve())
    assert workspace.connectors == ["filesystem", "memory"]


def test_missing_backend_actionable_fail(tmp_path):
    workspace_path = _write_workspace(tmp_path, architect="missing")

    with pytest.raises(WorkspaceLoadError, match="Unknown backend adapter 'missing'"):
        load_workspace(workspace_path)


def test_compose_binds_workspace_runtime(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_ARCHITECT", raising=False)
    monkeypatch.delenv("LLM_EXECUTOR", raising=False)
    skill_package = _write_skill_package(tmp_path)
    workspace_path = _write_workspace(tmp_path, skills=[str(skill_package)])

    composed = compose_workspace(load_workspace(workspace_path))

    assert composed.backend_binding.architect == "cli/codex"
    assert composed.backend_binding.executor == "cli/codex"
    assert composed.backend_binding.profile_name == "workspace:demo"
    assert composed.skill_registry.get("hello_skill") is not None
    assert composed.connector_registry.resolve("filesystem").name == "filesystem"
    assert composed.connector_registry.resolve("memory").name == "markdown_vault"
    assert composed.memory_connector.name == "markdown_vault"
    assert composed.policy.rules == {"mode": "local"}
    assert "Use the workspace context." in composed.hot_context
    assert composed.limits == {"recursion_limit": 7}
    assert "LLM_ARCHITECT" not in os.environ


def test_public_read_only_workspace_has_no_default_file_or_shell_tools(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("LLM_ARCHITECT", raising=False)
    monkeypatch.delenv("LLM_EXECUTOR", raising=False)
    skill_package = _write_skill_package(tmp_path)
    workspace_path = _write_workspace(
        tmp_path,
        skills=[str(skill_package)],
        policy_mode="public-read-only",
    )

    composed = compose_workspace(load_workspace(workspace_path))

    assert composed.skill_registry.names() == ["hello_skill"]
    assert composed.skill_registry.get("read_file") is None
    assert composed.skill_registry.get("write_file") is None
    assert composed.skill_registry.get("bash") is None


def test_department_metadata_only(tmp_path):
    workspace_path = _write_workspace(
        tmp_path,
        department="People Operations",
        organization="Any Organization String",
    )

    workspace = load_workspace(workspace_path)

    assert workspace.workspace.department == "People Operations"
    assert workspace.workspace.organization == "Any Organization String"


@pytest.mark.anyio
async def test_no_workspace_backward_compat(monkeypatch):
    monkeypatch.setattr(
        "agent_os.profiles.load_profiles",
        lambda: SimpleNamespace(default=None, profiles={}),
    )

    class CompletedGraph:
        def __init__(self):
            self.calls = []

        async def astream_events(self, state, config, version):
            self.calls.append((state, config, version))
            yield {"event": "unknown"}

        async def aget_state(self, config):
            return SimpleNamespace(created_at="now", values={"task": "done"}, next=(), tasks=())

    graph = CompletedGraph()
    console = Console(file=io.StringIO(), force_terminal=False, color_system=None)

    code = await async_main(
        ["task", "--thread-id", "no-workspace"],
        graph_factory=lambda: graph,
        console=console,
    )

    state, config, _ = graph.calls[0]
    assert code == 0
    assert state["hot_context"] is None
    assert "workspace" not in config["configurable"]


def test_both_reference_workspaces_load():
    root = Path(__file__).resolve().parents[1]
    workspace_paths = [
        root / "examples" / "coding-maintainer" / "workspace.toml",
        root / "examples" / "knowledge-assistant" / "workspace.toml",
    ]

    for workspace_path in workspace_paths:
        workspace = load_workspace(workspace_path)
        composed = compose_workspace(workspace)

        assert composed.workspace.workspace.name
        assert composed.memory_connector.name == "markdown_vault"
        assert composed.hot_context
