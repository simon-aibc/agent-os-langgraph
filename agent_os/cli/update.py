"""CLI handler for `agent-os update`.

Supports:
- Dry-run update check (`--check`)
- Safe pre-update DB backups
- Docker container detection vs Pip/Wheel environment
- Optional automated execution with `--yes`
- Daemon reload guidance
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB
from agent_os.migrations import (
    PERMISSIONS_MIGRATIONS,
    RUNS_MIGRATIONS,
    backup_database,
    run_migrations,
)
from agent_os.observations import DEFAULT_OBSERVATION_DB, OBSERVATION_DB_ENV
from agent_os.permission_store import DEFAULT_PERMISSION_DB, PERMISSION_DB_ENV
from agent_os.runs import _get_db_path as get_runs_db_path
from agent_os.schedules import _get_db_path as get_sched_db_path
from agent_os.update_check import check_for_update


def is_docker_environment() -> bool:
    """Return True if running inside a Docker container."""
    if Path("/.dockerenv").exists():
        return True
    if Path("/run/.containerenv").exists():
        return True
    if os.getenv("CONTAINER") == "docker":
        return True
    return False


def run_pre_update_db_backups() -> list[str]:
    """Execute pre-migration checks and backups on all known SQLite databases."""
    db_configs: list[tuple[str, tuple[Any, ...]]] = [
        (get_runs_db_path(), RUNS_MIGRATIONS),
        (get_sched_db_path(), ()),
        (os.getenv(PERMISSION_DB_ENV, DEFAULT_PERMISSION_DB), PERMISSIONS_MIGRATIONS),
        (os.getenv(OBSERVATION_DB_ENV, DEFAULT_OBSERVATION_DB), ()),
    ]

    checkpoint_db = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
    if checkpoint_db != ":memory:":
        db_configs.append((checkpoint_db, ()))

    backed_up: list[str] = []
    for db_path_str, migrations in db_configs:
        if db_path_str == ":memory:":
            continue
        p = Path(db_path_str).expanduser()
        if p.exists() and p.is_file():
            try:
                # 1. Explicitly backup database before update
                backup_path = backup_database(p)
                if backup_path:
                    backed_up.append(str(p))
            except Exception:
                pass
            try:
                # 2. Run schema migrations
                run_migrations(p, migrations=migrations, baseline_version=1)
            except Exception:
                pass
    return backed_up


def handle_update_command(
    args: argparse.Namespace, console: Console | None = None
) -> int:
    """Entrypoint for the `agent-os update` command."""
    out = console or Console()
    force_check = getattr(args, "check", False) or getattr(args, "force", False)
    info = check_for_update(force=force_check)

    out.print(f"[bold]Current Version:[/bold] {info.current_version}")
    out.print(f"[bold]Latest Version:[/bold]  {info.latest_version}")

    if getattr(args, "check", False):
        if info.update_available:
            out.print(
                f"[bold green]Update available![/bold green] ({info.current_version} -> {info.latest_version})"
            )
            if info.release_url:
                out.print(f"Release URL: {info.release_url}")
        else:
            out.print("[green]agent-os is up to date.[/green]")
        return 0

    if not info.update_available and not getattr(args, "force", False):
        out.print("[green]agent-os is already up to date.[/green]")
        return 0

    out.print("\n[bold cyan]1. Preparing database backup...[/bold cyan]")
    backed_up = run_pre_update_db_backups()
    if backed_up:
        for db in backed_up:
            out.print(f"  ✓ Verified/backed up database: {db}")
    else:
        out.print("  • No local SQLite databases found to backup.")

    out.print("\n[bold cyan]2. Update procedure:[/bold cyan]")
    if is_docker_environment():
        out.print("Detected Docker container runtime.")
        out.print("To update the container image, run:")
        out.print("  [bold yellow]docker compose pull && docker compose up -d[/bold yellow]")
    else:
        out.print("To update your Python package installation, run:")
        out.print("  [bold yellow]pip install --upgrade agent-os-langgraph[/bold yellow]")
        if getattr(args, "yes", False):
            out.print("\n[bold cyan]Executing pip upgrade...[/bold cyan]")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "agent-os-langgraph"]
                )
                out.print("[bold green]✓ Successfully upgraded agent-os-langgraph[/bold green]")
            except Exception as e:
                out.print(f"[bold red]Failed to run pip upgrade: {e}[/bold red]")
                return 1

    out.print("\n[bold cyan]3. Post-update instructions:[/bold cyan]")
    out.print("If you run the background daemon or web server, restart it now:")
    out.print("  [dim]pkill -f 'agent-os server' && agent-os server[/dim]\n")
    return 0
