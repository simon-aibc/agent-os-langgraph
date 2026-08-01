import subprocess

from langchain_core.tools import tool

from agent_os.output_limits import BASH_OUTPUT_MAX_BYTES, truncate_utf8
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
    This caps retained results after subprocess.run; capture_output still
    buffers process output and is not full OS-level OOM isolation.
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
        stdout, trunc_out = truncate_utf8(result.stdout, BASH_OUTPUT_MAX_BYTES)
        stderr, trunc_err = truncate_utf8(result.stderr, BASH_OUTPUT_MAX_BYTES)
        return BashResult(
            args=cmd_args,
            returncode=result.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            truncated=trunc_out or trunc_err,
        )
    except subprocess.TimeoutExpired as e:
        # e.stdout and e.stderr can be bytes or str, handle them gracefully
        raw_out = (
            e.stdout.decode("utf-8", errors="replace")
            if isinstance(e.stdout, bytes)
            else str(e.stdout or "")
        )
        raw_err = (
            e.stderr.decode("utf-8", errors="replace")
            if isinstance(e.stderr, bytes)
            else str(e.stderr or "")
        )
        stdout, trunc_out = truncate_utf8(raw_out, BASH_OUTPUT_MAX_BYTES)
        stderr, trunc_err = truncate_utf8(raw_err, BASH_OUTPUT_MAX_BYTES)
        return BashResult(
            args=cmd_args,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            truncated=trunc_out or trunc_err,
        )
    except FileNotFoundError as e:
        # For example, if the executable doesn't exist
        stderr, truncated = truncate_utf8(str(e), BASH_OUTPUT_MAX_BYTES)
        return BashResult(
            args=cmd_args,
            returncode=-1,
            stdout="",
            stderr=stderr,
            timed_out=False,
            truncated=truncated,
        )
