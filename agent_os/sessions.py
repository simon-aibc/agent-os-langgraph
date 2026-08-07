import contextlib
import datetime as dt
import os
import sqlite3
from typing import Any

from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB


def _get_db_path() -> str:
    return os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)

def _init_db() -> None:
    path = _get_db_path()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                thread_id TEXT PRIMARY KEY,
                created_at TEXT,
                last_turn_at TEXT,
                turn_count INTEGER,
                title TEXT
            )
        """)
        conn.commit()

def upsert_session(thread_id: str, title: str | None = None) -> None:
    _init_db()
    path = _get_db_path()
    now = dt.datetime.now(dt.UTC).isoformat()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        cursor = conn.execute(
            "SELECT created_at, turn_count, title FROM sessions WHERE thread_id = ?",
            (thread_id,)
        )
        row = cursor.fetchone()
        if row:
            _, turn_count, existing_title = row
            new_title = title if title is not None else existing_title
            conn.execute("""
                UPDATE sessions 
                SET last_turn_at = ?, turn_count = ?, title = ?
                WHERE thread_id = ?
            """, (now, turn_count + 1, new_title, thread_id))
        else:
            conn.execute("""
                INSERT INTO sessions (thread_id, created_at, last_turn_at, turn_count, title)
                VALUES (?, ?, ?, ?, ?)
            """, (thread_id, now, now, 1, title or "New Session"))
        conn.commit()

def list_sessions() -> list[dict[str, Any]]:
    _init_db()
    path = _get_db_path()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM sessions ORDER BY last_turn_at DESC")
        return [dict(row) for row in cursor.fetchall()]

def get_session(thread_id: str) -> dict[str, Any] | None:
    _init_db()
    path = _get_db_path()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM sessions WHERE thread_id = ?", (thread_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_session(thread_id: str) -> None:
    _init_db()
    path = _get_db_path()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute("DELETE FROM sessions WHERE thread_id = ?", (thread_id,))
        conn.commit()
