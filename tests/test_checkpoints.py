import sqlite3
from contextlib import closing

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from agent_os.checkpoints import CHECKPOINT_DB_ENV, get_default_checkpointer


def test_get_default_checkpointer_uses_configured_path(tmp_path, monkeypatch):
    database_path = tmp_path / "nested" / "workflow.db"
    monkeypatch.setenv(CHECKPOINT_DB_ENV, str(database_path))

    checkpointer = get_default_checkpointer()

    assert isinstance(checkpointer, SqliteSaver)
    assert database_path.exists()
    assert checkpointer.conn.execute("PRAGMA journal_mode").fetchone() is not None
    checkpointer.conn.close()


def test_get_default_checkpointer_accepts_explicit_path(tmp_path, monkeypatch):
    environment_path = tmp_path / "ignored.db"
    explicit_path = tmp_path / "explicit.db"
    monkeypatch.setenv(CHECKPOINT_DB_ENV, str(environment_path))

    checkpointer = get_default_checkpointer(explicit_path)

    assert explicit_path.exists()
    assert not environment_path.exists()
    checkpointer.conn.close()


def test_get_default_checkpointer_rejects_blank_environment(monkeypatch):
    monkeypatch.setenv(CHECKPOINT_DB_ENV, "   ")

    with pytest.raises(ValueError, match=f"{CHECKPOINT_DB_ENV} must not be empty"):
        get_default_checkpointer()


def test_closed_checkpointer_releases_database(tmp_path):
    database_path = tmp_path / "reusable.db"
    first = get_default_checkpointer(database_path)
    first.conn.close()

    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
