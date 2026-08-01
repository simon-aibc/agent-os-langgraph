import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

CHECKPOINT_DB_ENV = "AGENT_OS_CHECKPOINTS_DB"

_original_checkpoint_path = os.environ.get(CHECKPOINT_DB_ENV)
_checkpoint_directory = TemporaryDirectory(prefix="agent-os-pytest-")
os.environ[CHECKPOINT_DB_ENV] = str(
    Path(_checkpoint_directory.name) / "checkpoints.db"
)


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
    _checkpoint_directory.cleanup()
