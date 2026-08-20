import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

CHECKPOINT_DB_ENV = "AGENT_OS_CHECKPOINTS_DB"

_original_checkpoint_path = os.environ.get(CHECKPOINT_DB_ENV)
_checkpoint_directory = TemporaryDirectory(prefix="agent-os-pytest-")
_original_architect = os.environ.get("LLM_ARCHITECT")
_original_executor = os.environ.get("LLM_EXECUTOR")

os.environ["LLM_ARCHITECT"] = "offline/architect"
os.environ["LLM_EXECUTOR"] = "offline/executor"
os.environ[CHECKPOINT_DB_ENV] = str(Path(_checkpoint_directory.name) / "checkpoints.db")


@pytest.fixture(scope="session", autouse=True)
def isolate_default_checkpoint_database():
    """Keep the module-level default graph database outside the repository."""
    yield

    from agent_os.graph import graph

    graph.checkpointer.conn.close()
    if _original_checkpoint_path is None:
        os.environ.pop(CHECKPOINT_DB_ENV, None)
    else:
        os.environ[CHECKPOINT_DB_ENV] = _original_checkpoint_path

    for key, val in (
        ("LLM_ARCHITECT", _original_architect),
        ("LLM_EXECUTOR", _original_executor),
    ):
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val

    _checkpoint_directory.cleanup()
