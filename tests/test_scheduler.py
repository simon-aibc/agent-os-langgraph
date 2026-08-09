"""Tests for the scheduler dispatcher, tick, and service (r1.8a.3)."""

from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_os import runs
from agent_os.checkpoints import CHECKPOINT_DB_ENV
from agent_os.scheduler import (
    ScheduleDispatchResult,
    SchedulerService,
    dispatch_schedule,
)
from agent_os.schedules import (
    SCHED_DB_ENV,
    create_schedule,
    get_schedule,
)

# ── dispatch_schedule ───────────────────────────────────────────────


@pytest.fixture
def run_schedule():
    """A minimal run schedule dict as returned by claim_due_schedules."""
    return {
        "schedule_id": "sched-1",
        "name": "test run",
        "kind": "run",
        "trigger_kind": "interval",
        "trigger_value": "30m",
        "timezone": "UTC",
        "payload": {"task": "refactor code", "workspace": "/ws"},
        "enabled": True,
        "next_run_at": "2026-01-01T12:00:00+00:00",
    }


@pytest.fixture
def brief_schedule():
    """A minimal brief schedule dict."""
    return {
        "schedule_id": "sched-2",
        "name": "test brief",
        "kind": "brief",
        "trigger_kind": "interval",
        "trigger_value": "24h",
        "timezone": "UTC",
        "payload": {},
        "enabled": True,
        "next_run_at": "2026-01-01T12:00:00+00:00",
    }


@pytest.mark.anyio
async def test_dispatch_run_schedule(run_schedule):
    with (
        patch("agent_os.scheduler.runs") as mock_runs,
        patch("agent_os.scheduler.execute_run", new_callable=AsyncMock) as mock_exec,
        patch("agent_os.scheduler.record_schedule_result") as mock_record,
    ):
        mock_runs.create_run.return_value = "run-123"
        mock_runs.get_run.return_value = {"status": "completed"}

        result = await dispatch_schedule(run_schedule)

        assert isinstance(result, ScheduleDispatchResult)
        assert result.schedule_id == "sched-1"
        assert result.kind == "run"
        assert result.status == "completed"
        assert result.run_id == "run-123"
        assert result.error is None

        # Verify create_run was called with fresh thread/run IDs.
        mock_runs.create_run.assert_called_once()
        call_args = mock_runs.create_run.call_args
        assert call_args[0][1] == "/ws"  # workspace
        assert call_args[0][2] == "refactor code"  # task

        # Verify execute_run was called.
        mock_exec.assert_called_once()

        # Verify result was recorded.
        mock_record.assert_called_once_with(
            "sched-1", status="completed", error=None
        )


@pytest.mark.anyio
async def test_dispatch_brief_schedule(brief_schedule):
    with (
        patch("agent_os.scheduler.execute_brief") as mock_brief,
        patch("agent_os.scheduler.record_schedule_result") as mock_record,
    ):
        mock_brief.return_value = MagicMock(
            ref="AI/Briefs/2026-01-01.md",
            content="# Brief",
        )

        result = await dispatch_schedule(brief_schedule)

        assert result.kind == "brief"
        assert result.status == "completed"
        assert result.ref == "AI/Briefs/2026-01-01.md"
        mock_record.assert_called_once()


@pytest.mark.anyio
async def test_dispatch_run_error_is_captured(run_schedule):
    with (
        patch("agent_os.scheduler.runs") as mock_runs,
        patch(
            "agent_os.scheduler.execute_run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
        patch("agent_os.scheduler.record_schedule_result") as mock_record,
    ):
        mock_runs.create_run.return_value = "run-err"
        result = await dispatch_schedule(run_schedule)

        assert result.status == "error"
        assert "boom" in (result.error or "")
        mock_record.assert_called_once()


@pytest.mark.anyio
async def test_dispatch_uses_fresh_thread_ids(run_schedule):
    """Each dispatch should generate a unique thread_id."""
    thread_ids = set()

    with (
        patch("agent_os.scheduler.runs") as mock_runs,
        patch("agent_os.scheduler.execute_run", new_callable=AsyncMock),
        patch("agent_os.scheduler.record_schedule_result"),
    ):
        mock_runs.create_run.return_value = "run-1"
        mock_runs.get_run.return_value = {"status": "completed"}

        for _ in range(3):
            await dispatch_schedule(run_schedule)
            call_args = mock_runs.create_run.call_args
            thread_ids.add(call_args[0][0])

    assert len(thread_ids) == 3


# ── SchedulerService ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_scheduler_service_start_stop():
    service = SchedulerService()
    service.start()
    assert service._loop_task is not None
    await service.stop()
    assert service._loop_task is None


@pytest.mark.anyio
async def test_scheduler_tick_dispatches_due_schedules():
    now = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    fake_schedule = {
        "schedule_id": "s1",
        "name": "tick test",
        "kind": "run",
        "payload": {"task": "tick task"},
        "trigger_kind": "interval",
        "trigger_value": "1h",
        "timezone": "UTC",
        "enabled": True,
        "next_run_at": "2026-01-01T11:00:00+00:00",
    }

    with (
        patch("agent_os.scheduler.claim_due_schedules") as mock_claim,
        patch("agent_os.scheduler.dispatch_schedule", new_callable=AsyncMock) as mock_dispatch,
    ):
        mock_claim.return_value = [fake_schedule]
        mock_dispatch.return_value = ScheduleDispatchResult(
            schedule_id="s1", kind="run", status="completed"
        )

        service = SchedulerService()
        service._running = True
        await service.tick(now=now)

        mock_claim.assert_called_once_with(now, limit=10)
        assert len(service._child_tasks) == 1

        # Await the child tasks to clean up
        await asyncio.gather(*service._child_tasks)
        mock_dispatch.assert_called_once()
        # Task callback should have removed it
        assert len(service._child_tasks) == 0


@pytest.mark.anyio
async def test_scheduler_tick_respects_capacity():
    now = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)

    with (
        patch("agent_os.scheduler.claim_due_schedules") as mock_claim,
        patch("agent_os.scheduler.dispatch_schedule", new_callable=AsyncMock),
    ):
        mock_claim.return_value = []

        service = SchedulerService()
        service._running = True

        # Fill capacity
        for _ in range(5):
            service._child_tasks.add(asyncio.create_task(asyncio.sleep(0.01)))

        await service.tick(now=now)
        mock_claim.assert_called_once_with(now, limit=5)

        await service.stop()


@pytest.mark.anyio
async def test_scheduler_tick_capacity_exhausted():
    with patch("agent_os.scheduler.claim_due_schedules") as mock_claim:
        service = SchedulerService()
        service._running = True

        # Overfill capacity
        for _ in range(10):
            service._child_tasks.add(asyncio.create_task(asyncio.sleep(0.01)))

        await service.tick()
        mock_claim.assert_not_called()

        await service.stop()


@pytest.mark.anyio
async def test_scheduler_concurrent_dispatch():
    """Verify that multiple jobs are dispatched concurrently, not sequentially."""
    service = SchedulerService()
    service._running = True

    async def slow_dispatch(schedule: dict):
        await asyncio.sleep(0.1)
        return ScheduleDispatchResult(
            schedule_id=schedule["schedule_id"], kind="run", status="completed"
        )

    fake_schedules = [{"schedule_id": "s1"}, {"schedule_id": "s2"}, {"schedule_id": "s3"}]
    with patch("agent_os.scheduler.claim_due_schedules") as mock_claim:
        mock_claim.return_value = fake_schedules
        with patch("agent_os.scheduler.dispatch_schedule", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.side_effect = slow_dispatch

            start = dt.datetime.now()
            await service.tick()
            end = dt.datetime.now()

            # The tick itself should return almost immediately without waiting for children.
            assert (end - start).total_seconds() < 0.05

            # The tasks should be concurrently running.
            assert len(service._child_tasks) == 3

            # Wait for them to finish
            await asyncio.gather(*service._child_tasks)
            assert mock_dispatch.call_count == 3


@pytest.mark.anyio
async def test_scheduler_stop_drains_active_dispatches():
    """Shutdown waits for claimed work instead of cancelling side effects."""
    service = SchedulerService()
    service._running = True
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocking_dispatch(schedule: dict):
        started.set()
        await release.wait()
        return ScheduleDispatchResult(
            schedule_id=schedule["schedule_id"],
            kind="brief",
            status="completed",
        )

    with (
        patch(
            "agent_os.scheduler.claim_due_schedules",
            return_value=[{"schedule_id": "s_shutdown", "kind": "brief"}],
        ),
        patch(
            "agent_os.scheduler.dispatch_schedule",
            new=AsyncMock(side_effect=blocking_dispatch),
        ),
    ):
        await service.tick()
        await started.wait()

        stop_task = asyncio.create_task(service.stop())
        await asyncio.sleep(0)
        assert not stop_task.done()

        release.set()
        await stop_task
        assert service._child_tasks == set()


@pytest.mark.anyio
async def test_cancelled_run_dispatch_is_terminal(tmp_path, monkeypatch):
    """External cancellation leaves a complete, inspectable run record."""
    monkeypatch.setenv(CHECKPOINT_DB_ENV, str(tmp_path / "checkpoints.db"))
    monkeypatch.delenv(SCHED_DB_ENV, raising=False)
    schedule_id = create_schedule(
        name="cancelled run",
        kind="run",
        trigger_kind="interval",
        trigger_value="1h",
        payload={"task": "slow work"},
    )
    schedule = get_schedule(schedule_id)
    assert schedule is not None

    started = asyncio.Event()

    async def blocking_execute(run_id, thread_id, task):
        runs.set_status(run_id, "running")
        started.set()
        await asyncio.Event().wait()

    with patch(
        "agent_os.scheduler.execute_run",
        new=AsyncMock(side_effect=blocking_execute),
    ):
        dispatch_task = asyncio.create_task(dispatch_schedule(schedule))
        await started.wait()
        dispatch_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await dispatch_task

    run = runs.list_runs(limit=1)[0]
    assert run["status"] == "error"
    assert run["error"] == "Scheduler shutdown"
    assert run["ended_at"] is not None
    events = runs.list_events(run["run_id"])
    assert events[-1]["kind"] == "error"
    assert events[-1]["payload"] == {"message": "Scheduler shutdown"}

    updated_schedule = get_schedule(schedule_id)
    assert updated_schedule is not None
    assert updated_schedule["last_status"] == "error"
    assert updated_schedule["last_error"] == "Scheduler shutdown"


@pytest.mark.anyio
async def test_scheduler_service_failure_isolation():
    """A tick failure must not kill the service."""
    with patch(
        "agent_os.scheduler.claim_due_schedules",
        side_effect=RuntimeError("tick boom"),
    ):
        service = SchedulerService()
        service._running = True
        # tick() should log the error, not raise.
        await service.tick()


@pytest.mark.anyio
async def test_scheduler_service_disabled(monkeypatch):
    monkeypatch.setenv("AGENT_OS_SCHEDULER_ENABLED", "false")
    service = SchedulerService()
    assert not service.enabled
