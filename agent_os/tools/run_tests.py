import sys

from langchain_core.tools import tool

from agent_os.schemas import BashResult
from agent_os.tools.bash import bash


@tool
def run_tests(
    pytest_args: list[str] | None = None,
    timeout_seconds: int = 120,
) -> BashResult:
    """
    Execute pytest within the sandbox.
    Uses the bounded bash tool to ensure safe execution inside the sandbox.
    """
    args = [sys.executable, "-m", "pytest"]
    if pytest_args:
        args.extend(pytest_args)

    return bash.invoke({"cmd_args": args, "timeout_seconds": timeout_seconds})
