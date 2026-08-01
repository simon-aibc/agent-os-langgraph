from langchain_core.tools import tool

from agent_os.sandbox import get_read_root
from agent_os.schemas import ReadFileResult


@tool
def read_file(path: str) -> ReadFileResult:
    """Read UTF-8 text from a file within the project."""
    root = get_read_root()
    target = (root / path).resolve()

    if not target.is_relative_to(root):
        raise ValueError("Path is outside project root")

    if not target.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    content = target.read_text(encoding="utf-8")
    return ReadFileResult(path=str(path), content=content)
