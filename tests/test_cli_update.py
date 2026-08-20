import argparse
from unittest.mock import patch

from rich.console import Console

from agent_os.cli.app import build_parser
from agent_os.cli.update import (
    handle_update_command,
    is_docker_environment,
)
from agent_os.update_check import UpdateInfo


def test_cli_update_parser_registration():
    parser = build_parser()
    args = parser.parse_args(["update", "--check"])
    assert args.command == "update"
    assert args.check is True
    assert args.yes is False


def test_docker_environment_detection(monkeypatch, tmp_path):
    assert not is_docker_environment()

    # Mock container environment
    monkeypatch.setenv("CONTAINER", "docker")
    assert is_docker_environment()


def test_handle_update_check_flag():
    console = Console(record=True)
    args = argparse.Namespace(
        check=True, force=False, yes=False, pull=False, reload=False
    )

    mock_info = UpdateInfo(
        current_version="2.2.0",
        latest_version="2.3.0",
        update_available=True,
        release_url="https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v2.3.0",
    )

    with patch("agent_os.cli.update.check_for_update", return_value=mock_info):
        code = handle_update_command(args, console=console)
        assert code == 0
        text = console.export_text()
        assert "Current Version: 2.2.0" in text
        assert "Latest Version:  2.3.0" in text
        assert "Update available!" in text


def test_handle_update_pip_guidance():
    console = Console(record=True)
    args = argparse.Namespace(
        check=False, force=False, yes=False, pull=False, reload=False
    )

    mock_info = UpdateInfo(
        current_version="2.2.0",
        latest_version="2.3.0",
        update_available=True,
    )

    with (
        patch("agent_os.cli.update.check_for_update", return_value=mock_info),
        patch("agent_os.cli.update.is_docker_environment", return_value=False),
        patch(
            "agent_os.cli.update.run_pre_update_db_backups", return_value=["test.db"]
        ),
    ):
        code = handle_update_command(args, console=console)
        assert code == 0
        text = console.export_text()
        assert "pip install --upgrade agent-os-langgraph" in text
        assert "Verified/backed up database: test.db" in text


def test_handle_update_docker_guidance():
    console = Console(record=True)
    args = argparse.Namespace(
        check=False, force=False, yes=False, pull=False, reload=False
    )

    mock_info = UpdateInfo(
        current_version="2.2.0",
        latest_version="2.3.0",
        update_available=True,
    )

    with (
        patch("agent_os.cli.update.check_for_update", return_value=mock_info),
        patch("agent_os.cli.update.is_docker_environment", return_value=True),
        patch("agent_os.cli.update.run_pre_update_db_backups", return_value=[]),
    ):
        code = handle_update_command(args, console=console)
        assert code == 0
        text = console.export_text()
        assert "Detected Docker container runtime." in text
        assert "docker compose pull && docker compose up -d" in text
