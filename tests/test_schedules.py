"""Tests for the schedule store and recurrence engine (r1.8a.1).

Covers schema, CRUD, filtering, validation, payload round-trip,
interval/cron/timezone boundaries, coalescing, and atomic claim
behaviour.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from agent_os.checkpoints import CHECKPOINT_DB_ENV
from agent_os.schedule_recurrence import (
    coalesce_next_run,
    next_run_at,
    parse_interval,
    validate_cron,
)
from agent_os.schedules import (
    SCHED_DB_ENV,
    _get_db_path,
    _init_schedules_db,
    claim_due_schedules,
    create_schedule,
    get_schedule,
    list_schedules,
    record_schedule_result,
    remove_schedule,
    set_schedule_enabled,
)

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def sched_db(tmp_path, monkeypatch):
    """Isolate the scheduler DB to a temp directory."""
    monkeypatch.setenv(CHECKPOINT_DB_ENV, str(tmp_path / "checkpoints.db"))
    monkeypatch.delenv(SCHED_DB_ENV, raising=False)
    return Path(_get_db_path())


# ── Schema tests ────────────────────────────────────────────────────


def test_init_creates_schedules_table(sched_db):
    _init_schedules_db()
    with contextlib.closing(sqlite3.connect(sched_db)) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schedules'"
        )
        assert cursor.fetchone() is not None


def test_init_creates_due_index(sched_db):
    _init_schedules_db()
    with contextlib.closing(sqlite3.connect(sched_db)) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name = 'schedules_due_idx'"
        )
        assert cursor.fetchone() is not None


def test_init_is_idempotent(sched_db):
    _init_schedules_db()
    _init_schedules_db()  # Second call must not raise.


# ── Interval parsing ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value, expected_seconds",
    [
        ("30", 30),
        ("30s", 30),
        ("5m", 300),
        ("2h", 7200),
        ("1d", 86400),
        ("60S", 60),  # Case insensitive.
        (" 10s ", 10),  # Whitespace trimming.
    ],
)
def test_parse_interval_valid(value, expected_seconds):
    assert parse_interval(value) == dt.timedelta(seconds=expected_seconds)


@pytest.mark.parametrize(
    "value",
    ["", "abc", "-5s", "0s", "1w", "5 minutes", "1.5h"],
)
def test_parse_interval_invalid(value):
    with pytest.raises(ValueError):
        parse_interval(value)


# ── Cron validation ─────────────────────────────────────────────────


def test_validate_cron_valid():
    validate_cron("0 9 * * *", "UTC")
    validate_cron("*/5 * * * *", "America/New_York")


def test_validate_cron_invalid_expression():
    with pytest.raises(ValueError, match="Invalid cron"):
        validate_cron("invalid cron", "UTC")


def test_validate_cron_invalid_timezone():
    with pytest.raises(ValueError, match="Unknown timezone"):
        validate_cron("0 9 * * *", "Not/A/Zone")


# ── next_run_at ─────────────────────────────────────────────────────


def test_next_run_at_interval():
    after = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    result = next_run_at("interval", "30m", "UTC", after=after)
    assert result == after + dt.timedelta(minutes=30)


def test_next_run_at_cron():
    # After noon UTC, the next 9:00 daily is the following day.
    after = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    result = next_run_at("cron", "0 9 * * *", "UTC", after=after)
    expected = dt.datetime(2026, 1, 2, 9, 0, 0, tzinfo=dt.UTC)
    assert result == expected


def test_next_run_at_cron_respects_timezone():
    # 09:00 in America/New_York is 14:00 UTC (EST, no DST).
    after = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    result = next_run_at("cron", "0 9 * * *", "America/New_York", after=after)
    # Next occurrence: Jan 2 at 09:00 EST = 14:00 UTC.
    assert result.tzinfo == dt.UTC or result.utcoffset() == dt.timedelta(0)
    assert result.hour == 14
    assert result.day == 1


def test_next_run_at_unknown_trigger_kind():
    with pytest.raises(ValueError, match="Unknown trigger_kind"):
        next_run_at(
            "unknown",  # type: ignore
            "value",
            "UTC",
            after=dt.datetime.now(dt.UTC),
        )


def test_validate_cron_six_fields():
    with pytest.raises(ValueError, match="must have exactly 5 fields"):
        validate_cron("0 0 9 * * *", "UTC")


def test_coalesce_next_run_long_gap():
    persisted = dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=dt.UTC)
    now = dt.datetime(2026, 2, 1, 0, 0, 0, tzinfo=dt.UTC)  # 1 month later

    # For interval, it should add interval without looping
    res = coalesce_next_run("interval", "1h", "UTC", persisted=persisted, now=now)
    assert res == now + dt.timedelta(hours=1)

    # For cron, it should jump to next occurrence
    res_cron = coalesce_next_run("cron", "0 * * * *", "UTC", persisted=persisted, now=now)
    assert res_cron == now + dt.timedelta(hours=1)


# ── Coalescing ──────────────────────────────────────────────────────


def test_coalesce_skips_missed_fires():
    # Schedule fires every 1 hour. Last persisted was 3 hours ago.
    persisted = dt.datetime(2026, 1, 1, 6, 0, 0, tzinfo=dt.UTC)
    now = dt.datetime(2026, 1, 1, 9, 30, 0, tzinfo=dt.UTC)
    result = coalesce_next_run(
        "interval", "1h", "UTC", persisted=persisted, now=now
    )
    # Should be strictly after now.
    assert result > now
    assert result == dt.datetime(2026, 1, 1, 10, 0, 0, tzinfo=dt.UTC)


def test_coalesce_cron_missed_fires():
    # Daily at 09:00 UTC. Process was down for 3 days.
    persisted = dt.datetime(2026, 1, 1, 9, 0, 0, tzinfo=dt.UTC)
    now = dt.datetime(2026, 1, 4, 10, 0, 0, tzinfo=dt.UTC)
    result = coalesce_next_run(
        "cron", "0 9 * * *", "UTC", persisted=persisted, now=now
    )
    assert result > now
    assert result == dt.datetime(2026, 1, 5, 9, 0, 0, tzinfo=dt.UTC)


# ── CRUD ────────────────────────────────────────────────────────────


def test_create_and_get_schedule(sched_db):
    sid = create_schedule(
        name="daily-run",
        kind="run",
        trigger_kind="cron",
        trigger_value="0 9 * * *",
        timezone="UTC",
        payload={"task": "refactor code"},
    )
    sched = get_schedule(sid)
    assert sched is not None
    assert sched["name"] == "daily-run"
    assert sched["kind"] == "run"
    assert sched["trigger_kind"] == "cron"
    assert sched["trigger_value"] == "0 9 * * *"
    assert sched["timezone"] == "UTC"
    assert sched["payload"] == {"task": "refactor code"}
    assert sched["enabled"] is True
    assert sched["next_run_at"] is not None
    assert sched["last_run_at"] is None


def test_create_interval_brief_schedule(sched_db):
    sid = create_schedule(
        name="hourly-brief",
        kind="brief",
        trigger_kind="interval",
        trigger_value="1h",
    )
    sched = get_schedule(sid)
    assert sched is not None
    assert sched["kind"] == "brief"
    assert sched["trigger_kind"] == "interval"
    assert sched["payload"] == {}


def test_get_schedule_unknown(sched_db):
    _init_schedules_db()
    assert get_schedule("nonexistent-id") is None


def test_list_schedules_all(sched_db):
    create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    create_schedule(
        name="b1", kind="brief", trigger_kind="interval",
        trigger_value="24h",
    )
    all_schedules = list_schedules()
    assert len(all_schedules) == 2


def test_list_schedules_filter_by_kind(sched_db):
    create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    create_schedule(
        name="b1", kind="brief", trigger_kind="interval",
        trigger_value="24h",
    )
    runs = list_schedules(kind="run")
    assert len(runs) == 1
    assert runs[0]["kind"] == "run"
    briefs = list_schedules(kind="brief")
    assert len(briefs) == 1
    assert briefs[0]["kind"] == "brief"


def test_list_schedules_filter_by_enabled(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    set_schedule_enabled(sid, False)
    assert len(list_schedules(enabled=True)) == 0
    assert len(list_schedules(enabled=False)) == 1


def test_list_schedules_ordered_by_created_at_desc(sched_db):
    s1 = create_schedule(
        name="first", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    s2 = create_schedule(
        name="second", kind="run", trigger_kind="interval",
        trigger_value="1h", payload={"task": "t2"},
    )
    schedules = list_schedules()
    assert schedules[0]["schedule_id"] == s2
    assert schedules[1]["schedule_id"] == s1


def test_remove_schedule(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    assert remove_schedule(sid) is True
    assert get_schedule(sid) is None


def test_remove_schedule_unknown(sched_db):
    _init_schedules_db()
    assert remove_schedule("nonexistent-id") is False


def test_set_schedule_enabled(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    assert set_schedule_enabled(sid, False) is True
    assert get_schedule(sid)["enabled"] is False  # type: ignore[index]
    assert set_schedule_enabled(sid, True) is True
    assert get_schedule(sid)["enabled"] is True  # type: ignore[index]


def test_set_schedule_enabled_unknown(sched_db):
    _init_schedules_db()
    assert set_schedule_enabled("nonexistent-id", True) is False


# ── Validation ──────────────────────────────────────────────────────


def test_invalid_kind(sched_db):
    with pytest.raises(ValueError, match="kind must be"):
        create_schedule(
            name="bad", kind="webhook",  # type: ignore[arg-type]
            trigger_kind="interval", trigger_value="30m",
        )


def test_invalid_trigger_kind(sched_db):
    with pytest.raises(ValueError, match="trigger_kind must be"):
        create_schedule(
            name="bad", kind="run",
            trigger_kind="webhook",  # type: ignore[arg-type]
            trigger_value="30m", payload={"task": "t"},
        )


def test_interval_rejects_non_utc_timezone(sched_db):
    with pytest.raises(ValueError, match="non-UTC timezone"):
        create_schedule(
            name="bad", kind="run",
            trigger_kind="interval", trigger_value="30m",
            timezone="America/New_York",
            payload={"task": "t"},
        )


def test_run_requires_task_in_payload(sched_db):
    with pytest.raises(ValueError, match="task"):
        create_schedule(
            name="bad", kind="run",
            trigger_kind="interval", trigger_value="30m",
            payload={},
        )


def test_run_rejects_unknown_payload_keys(sched_db):
    with pytest.raises(ValueError, match="Unknown payload"):
        create_schedule(
            name="bad", kind="run",
            trigger_kind="interval", trigger_value="30m",
            payload={"task": "t", "extra": "nope"},
        )


def test_brief_rejects_unknown_payload_keys(sched_db):
    with pytest.raises(ValueError, match="Unknown payload"):
        create_schedule(
            name="bad", kind="brief",
            trigger_kind="interval", trigger_value="30m",
            payload={"task": "should not be here"},
        )


# ── Payload round-trip ──────────────────────────────────────────────


def test_payload_round_trip(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m",
        payload={"task": "test task", "workspace": "/some/path"},
    )
    sched = get_schedule(sid)
    assert sched is not None
    assert isinstance(sched["payload"], dict)
    assert sched["payload"]["task"] == "test task"
    assert sched["payload"]["workspace"] == "/some/path"


# ── Atomic claim ────────────────────────────────────────────────────


def test_claim_due_schedules(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    sched = get_schedule(sid)
    assert sched is not None
    # Simulate: pretend it's past the next_run_at.
    due_time = dt.datetime.fromisoformat(sched["next_run_at"]) + dt.timedelta(seconds=1)
    claimed = claim_due_schedules(due_time, limit=10)
    assert len(claimed) == 1
    assert claimed[0]["schedule_id"] == sid
    # The stored next_run_at should have advanced.
    updated = get_schedule(sid)
    assert updated is not None
    assert updated["next_run_at"] > sched["next_run_at"]


def test_claim_due_respects_limit(sched_db):
    for i in range(5):
        create_schedule(
            name=f"r{i}", kind="run", trigger_kind="interval",
            trigger_value="30m", payload={"task": f"t{i}"},
        )
    # Claim with a far-future time so all are due.
    far_future = dt.datetime(2099, 1, 1, tzinfo=dt.UTC)
    claimed = claim_due_schedules(far_future, limit=2)
    assert len(claimed) == 2


def test_claim_due_excludes_disabled(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    set_schedule_enabled(sid, False)
    far_future = dt.datetime(2099, 1, 1, tzinfo=dt.UTC)
    claimed = claim_due_schedules(far_future, limit=10)
    assert len(claimed) == 0


def test_claim_due_does_not_double_fire(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    sched = get_schedule(sid)
    assert sched is not None
    due_time = dt.datetime.fromisoformat(sched["next_run_at"]) + dt.timedelta(seconds=1)
    first = claim_due_schedules(due_time, limit=10)
    assert len(first) == 1
    # Second claim at the same time should find nothing.
    second = claim_due_schedules(due_time, limit=10)
    assert len(second) == 0


# ── Record result ───────────────────────────────────────────────────


def test_record_schedule_result(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    record_schedule_result(sid, status="completed")
    sched = get_schedule(sid)
    assert sched is not None
    assert sched["last_status"] == "completed"
    assert sched["last_error"] is None


def test_record_schedule_result_with_error(sched_db):
    sid = create_schedule(
        name="r1", kind="run", trigger_kind="interval",
        trigger_value="30m", payload={"task": "t1"},
    )
    record_schedule_result(sid, status="error", error="boom")
    sched = get_schedule(sid)
    assert sched is not None
    assert sched["last_status"] == "error"
    assert sched["last_error"] == "boom"
