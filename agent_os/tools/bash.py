import subprocess

from langchain_core.tools import tool

from agent_os.sandbox import get_sandbox_root
from agent_os.schemas import BashResult


@tool
def bash(cmd_args: list[str], timeout_seconds: int = 30) -> BashResult:
    """
    Execute a bounded subprocess in the sandbox.
    Rejects empty args. Does NOT use a shell, so no shell metacharacters
    or pipelines will be evaluated. This is for running specific commands
    safely and capturing their output.
    Note: sandbox cwd enforcement is not OS/container isolation.
    """
    if not cmd_args:
        raise ValueError("Args list cannot be empty")

    cwd = get_sandbox_root()
    cwd.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            cmd_args,
            cwd=cwd,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        return BashResult(
            args=cmd_args,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as e:
        # e.stdout and e.stderr can be bytes or str, handle them gracefully
        stdout = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else str(e.stdout or "")
        stderr = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else str(e.stderr or "")
        return BashResult(
            args=cmd_args,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )
    except FileNotFoundError as e:
        # For example, if the executable doesn't exist
        return BashResult(
            args=cmd_args,
            returncode=-1,
            stdout="",
            stderr=str(e),
            timed_out=False,
        )
