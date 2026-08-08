import contextlib
import datetime as dt
import json
import os
import sqlite3
import uuid
from typing import Any

from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB


def _get_db_path() -> str:
    return os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)


def _init_runs_db() -> None:
    path = _get_db_path()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                workspace TEXT,
                status TEXT NOT NULL,
                task TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                ended_at TEXT,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_events (
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (run_id, seq)
            )
        """)
        conn.commit()


def create_run(thread_id: str, workspace: str | None, task: str | None) -> str:
    _init_runs_db()
    path = _get_db_path()
    run_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC).isoformat()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, thread_id, workspace, status, task, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, thread_id, workspace, "queued", task, now, now),
        )
        conn.commit()
    return run_id


def append_event(run_id: str, kind: str, payload: dict[str, Any]) -> int:
    _init_runs_db()
    path = _get_db_path()
    ts = dt.datetime.now(dt.UTC).isoformat()
    serialized_payload = json.dumps(payload)
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM run_events WHERE run_id = ?",
            (run_id,),
        )
        seq = int(cursor.fetchone()[0])
        conn.execute(
            """
            INSERT INTO run_events (run_id, seq, ts, kind, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, seq, ts, kind, serialized_payload),
        )
        conn.commit()
    return seq


def set_status(
    run_id: str,
    status: str,
    *,
    error: str | None = None,
    ended: bool = False,
) -> None:
    _init_runs_db()
    path = _get_db_path()
    now = dt.datetime.now(dt.UTC).isoformat()
    ended_at = now if ended else None
    with contextlib.closing(sqlite3.connect(path)) as conn:
        if ended:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, updated_at = ?, ended_at = ?, error = ?
                WHERE run_id = ?
                """,
                (status, now, ended_at, error, run_id),
            )
        else:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, updated_at = ?, error = ?
                WHERE run_id = ?
                """,
                (status, now, error, run_id),
            )
        conn.commit()


def get_run(run_id: str) -> dict[str, Any] | None:
    _init_runs_db()
    path = _get_db_path()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_runs(
    *,
    status: str | None = None,
    workspace: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    _init_runs_db()
    path = _get_db_path()
    where = []
    params: list[Any] = []
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if workspace is not None:
        where.append("workspace = ?")
        params.append(workspace)

    query = "SELECT * FROM runs"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def list_events(run_id: str, *, after: int = 0) -> list[dict[str, Any]]:
    _init_runs_db()
    path = _get_db_path()
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT * FROM run_events
            WHERE run_id = ? AND seq > ?
            ORDER BY seq ASC
            """,
            (run_id, after),
        )
        events = []
        for row in cursor.fetchall():
            event = dict(row)
            event["payload"] = json.loads(event["payload"])
            events.append(event)
        return events
