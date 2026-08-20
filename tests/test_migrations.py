import sqlite3
from pathlib import Path

import pytest

from agent_os.migrations import (
    Migration,
    MigrationError,
    _is_safe_statement,
    run_migrations,
)


def test_is_safe_statement():
    assert _is_safe_statement("ALTER TABLE users ADD COLUMN age INTEGER")
    assert _is_safe_statement("CREATE TABLE IF NOT EXISTS items (id TEXT)")
    assert _is_safe_statement("CREATE INDEX IF NOT EXISTS idx_items ON items (id)")

    # Destructive statements must be rejected
    assert not _is_safe_statement("DROP TABLE users")
    assert not _is_safe_statement("ALTER TABLE users DROP COLUMN age")
    assert not _is_safe_statement("DROP INDEX idx_items")
    assert not _is_safe_statement("RENAME TO new_table")
    assert not _is_safe_statement("DELETE FROM users")
    assert not _is_safe_statement("TRUNCATE TABLE users")


def test_migrations_fresh_db_sets_baseline(tmp_path: Path):
    db_file = tmp_path / "test.db"

    applied = run_migrations(db_file, baseline_version=1)
    assert applied == []

    with sqlite3.connect(db_file) as conn:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == 1


def test_migrations_apply_and_idempotent(tmp_path: Path):
    db_file = tmp_path / "app.db"

    # Initial setup
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users VALUES ('u1', 'Alice')")
        conn.execute("PRAGMA user_version = 1")

    migrations = [
        Migration(
            id="0002_add_email",
            version=2,
            statements=("ALTER TABLE users ADD COLUMN email TEXT DEFAULT 'none'",),
            description="Add email column",
        ),
        Migration(
            id="0003_add_index",
            version=3,
            statements=("CREATE INDEX IF NOT EXISTS idx_users_name ON users(name)",),
            description="Add index on name",
        ),
    ]

    # Run migrations once
    applied = run_migrations(db_file, migrations)
    assert applied == ["0002_add_email", "0003_add_index"]

    # Check backup created
    backup_file = tmp_path / "app.db.bak-1"
    assert backup_file.exists()

    # Check schema updated and data intact
    with sqlite3.connect(db_file) as conn:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == 3
        row = conn.execute("SELECT id, name, email FROM users WHERE id='u1'").fetchone()
        assert row == ("u1", "Alice", "none")

    # Run again -> should be no-op (idempotent)
    applied_again = run_migrations(db_file, migrations)
    assert applied_again == []


def test_migration_fail_closed_rollback(tmp_path: Path):
    db_file = tmp_path / "fail.db"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, balance REAL)")
        conn.execute("INSERT INTO accounts VALUES ('acc1', 100.0)")
        conn.execute("PRAGMA user_version = 1")

    bad_migrations = [
        Migration(
            id="0002_add_currency",
            version=2,
            statements=("ALTER TABLE accounts ADD COLUMN currency TEXT DEFAULT 'USD'",),
        ),
        Migration(
            id="0003_broken_migration",
            version=3,
            statements=("SYNTAX ERROR IS NOT VALID SQL",),
        ),
    ]

    with pytest.raises(MigrationError):
        run_migrations(db_file, bad_migrations)

    # Verify rollback: version remains 1, column currency was rolled back
    with sqlite3.connect(db_file) as conn:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == 1
        cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        assert "currency" not in cols
        row = conn.execute("SELECT id, balance FROM accounts").fetchone()
        assert row == ("acc1", 100.0)

    # Verify backup exists
    assert (tmp_path / "fail.db.bak-1").exists()


def test_migration_disallows_destructive_ddl(tmp_path: Path):
    db_file = tmp_path / "destructive.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE secret (data TEXT)")
        conn.execute("PRAGMA user_version = 1")

    destructive = [
        Migration(
            id="0002_drop_table",
            version=2,
            statements=("DROP TABLE secret",),
        )
    ]

    with pytest.raises(MigrationError, match="Disallowed destructive DDL"):
        run_migrations(db_file, destructive)


def test_migration_in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test (id INT)")
    conn.execute("PRAGMA user_version = 0")

    migrations = [
        Migration(
            id="0001_add_col",
            version=1,
            statements=("ALTER TABLE test ADD COLUMN name TEXT",),
        )
    ]

    applied = run_migrations(conn, migrations)
    assert applied == ["0001_add_col"]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
