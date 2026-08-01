import json
import os
import subprocess
import sys
import time
from pathlib import Path

from agent_os.checkpoints import CHECKPOINT_DB_ENV

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER = Path(__file__).with_name("checkpoint_worker.py")


def worker_environment(database_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment[CHECKPOINT_DB_ENV] = str(database_path)
    return environment


def run_resume_worker(thread_id: str, database_path: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, str(WORKER), "resume", thread_id],
        cwd=PROJECT_ROOT,
        env=worker_environment(database_path),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(completed.stdout)


def start_pause_worker_and_kill(
    thread_id: str,
    database_path: Path,
    status_path: Path,
) -> dict:
    with subprocess.Popen(
        [sys.executable, str(WORKER), "pause", thread_id, str(status_path)],
        cwd=PROJECT_ROOT,
        env=worker_environment(database_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        deadline = time.monotonic() + 30
        try:
            while not status_path.exists():
                if process.poll() is not None:
                    _, stderr = process.communicate()
                    raise AssertionError(f"pause worker exited early: {stderr}")
                if time.monotonic() >= deadline:
                    raise AssertionError("pause worker did not reach human_gate")
                time.sleep(0.05)

            paused = json.loads(status_path.read_text(encoding="utf-8"))
            assert process.poll() is None
            process.kill()
            process.communicate(timeout=10)
            assert process.returncode != 0
            return paused
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)


def test_workflow_resumes_in_fresh_process_after_restart(tmp_path):
    database_path = tmp_path / "restart-checkpoints.db"
    status_path = tmp_path / "pause-status.json"
    thread_id = "simon-20260801-restart-proof"

    paused = start_pause_worker_and_kill(thread_id, database_path, status_path)

    assert paused["pid"] != os.getpid()
    assert paused["interrupted"] is True
    assert paused["next"] == ["human_gate"]
    assert paused["task"] == "prove workflow survives restart"
    assert database_path.exists()
    assert database_path.stat().st_size > 0

    resumed = run_resume_worker(thread_id, database_path)

    assert resumed["pid"] not in {os.getpid(), paused["pid"]}
    assert resumed["before_next"] == ["human_gate"]
    assert resumed["task"] == paused["task"]
    assert resumed["human_feedback"] == "approved"
    assert resumed["success"] is True
    assert resumed["verify_output"] == "cross-process verification passed"
    assert resumed["after_next"] == []
