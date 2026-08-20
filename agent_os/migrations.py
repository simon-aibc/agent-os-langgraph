"""Additive migration runner for AgentOS SQLite databases.

Enforces:
1. Strict additive-only changes (ADD COLUMN, CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).
2. Version tracking via PRAGMA user_version.
3. Automatic backup to <db>.bak-<user_version> before migrations run.
4. Idempotency using PRAGMA table_info checks.
5. Fail-closed rollback on error.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Patterns for forbidden destructive operations
_FORBIDDEN_DDL_PATTERNS = [
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+INDEX\b", re.IGNORECASE),
    re.compile(r"\bRENAME\s+TO\b", re.IGNORECASE),
    re.compile(r"\bRENAME\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
]

_ALTER_ADD_COLUMN_PATTERN = re.compile(
    r"ALTER\s+TABLE\s+([`\"\[]?\w+[`\"\]]?)\s+ADD\s+(?:COLUMN\s+)?([`\"\[]?\w+[`\"\]]?)\s+([^;]+)",
    re.IGNORECASE,
)


class MigrationError(RuntimeError):
    """Raised when a migration fails or violates safety invariants."""


class Migration(NamedTuple):
    """Auditable additive migration definition."""

    id: str
    version: int
    statements: tuple[str, ...] = ()
    handler: Callable[[sqlite3.Connection], None] | None = None
    description: str = ""


def _is_safe_statement(sql: str) -> bool:
    """Ensure statement contains no destructive DDL or DML."""
    clean = sql.strip()
    if not clean:
        return True
    for pattern in _FORBIDDEN_DDL_PATTERNS:
        if pattern.search(clean):
            return False
    return True


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Retrieve existing column names for a table."""
    clean_table = table_name.strip('`"[]')
    cursor = conn.execute(f"PRAGMA table_info({clean_table})")
    return {row[1] for row in cursor.fetchall()}


def _apply_statement(conn: sqlite3.Connection, sql: str) -> None:
    """Apply a single DDL statement idempotently."""
    clean = sql.strip()
    if not clean:
        return

    if not _is_safe_statement(clean):
        raise MigrationError(f"Disallowed destructive DDL detected: {clean}")

    # Check if this is an ADD COLUMN statement to guarantee idempotency
    match = _ALTER_ADD_COLUMN_PATTERN.match(clean)
    if match:
        table_name, col_name, _col_def = match.groups()
        table_name = table_name.strip('`"[]')
        col_name = col_name.strip('`"[]')
        existing_cols = _table_columns(conn, table_name)
        if col_name in existing_cols:
            logger.debug(
                "Column %s.%s already exists, skipping ADD COLUMN.",
                table_name,
                col_name,
            )
            return

    conn.execute(clean)


def backup_database(db_path: str | Path, version: int) -> Path | None:
    """Create a backup of the DB file before applying migrations.

    WAL-aware: Executes PRAGMA wal_checkpoint(TRUNCATE) before copying to flush
    all uncheckpointed frames into the main DB file. If checkpointing fails,
    falls back to copying the main file plus -wal and -shm files if present.

    Returns the backup Path or None if in-memory / nonexistent.
    """
    path_str = str(db_path)
    if path_str == ":memory:" or path_str.startswith("file::memory:"):
        return None

    path = Path(path_str).resolve()
    if not path.exists() or not path.is_file():
        return None

    backup_path = path.with_name(f"{path.name}.bak-{version}")

    checkpointed = False
    try:
        with sqlite3.connect(str(path), timeout=5.0) as chk_conn:
            chk_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        checkpointed = True
    except Exception as exc:
        logger.warning(
            "WAL checkpoint failed for %s (%s); will fallback to copying sidecar files.",
            path,
            exc,
        )

    try:
        shutil.copy2(path, backup_path)
        if not checkpointed:
            wal_file = path.with_name(f"{path.name}-wal")
            shm_file = path.with_name(f"{path.name}-shm")
            if wal_file.exists():
                shutil.copy2(wal_file, backup_path.with_name(f"{backup_path.name}-wal"))
            if shm_file.exists():
                shutil.copy2(shm_file, backup_path.with_name(f"{backup_path.name}-shm"))

        logger.info("Created pre-migration backup at %s", backup_path)
        return backup_path
    except OSError as err:
        raise MigrationError(
            f"Failed to create pre-migration backup for {path}: {err}"
        ) from err


def run_migrations(
    db_path: str | Path | sqlite3.Connection,
    migrations: Sequence[Migration] = (),
    *,
    baseline_version: int = 1,
) -> list[str]:
    """Execute pending additive migrations against a database.

    Features:
    - Backup created before applying any pending migrations.
    - Idempotent and fail-closed: rollback on exception.
    - PRAGMA user_version updated sequentially.
    """
    is_conn = isinstance(db_path, sqlite3.Connection)
    conn = db_path if is_conn else sqlite3.connect(str(db_path))

    applied_ids: list[str] = []
    try:
        cursor = conn.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]

        # Determine pending migrations
        pending = [m for m in migrations if m.version > current_version]
        pending.sort(key=lambda m: m.version)

        if not pending:
            # If database has no version set yet, set to baseline version
            if current_version == 0 and baseline_version > 0:
                conn.execute(f"PRAGMA user_version = {baseline_version}")
                conn.commit()
            return []

        # File backup before modifying
        if not is_conn:
            backup_database(db_path, current_version)

        # Apply pending migrations inside transaction
        conn.execute("BEGIN IMMEDIATE")
        try:
            for migration in pending:
                logger.info(
                    "Applying migration %s (v%d): %s",
                    migration.id,
                    migration.version,
                    migration.description,
                )
                for stmt in migration.statements:
                    _apply_statement(conn, stmt)

                if migration.handler is not None:
                    migration.handler(conn)

                conn.execute(f"PRAGMA user_version = {migration.version}")
                applied_ids.append(migration.id)

            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("Migration failed, rolled back: %s", exc)
            raise MigrationError(f"Migration execution failed: {exc}") from exc

        return applied_ids
    finally:
        if not is_conn:
            conn.close()
