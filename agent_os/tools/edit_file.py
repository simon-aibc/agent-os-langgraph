from langchain_core.tools import tool

from agent_os.sandbox import resolve_sandbox_path
from agent_os.schemas import EditFileResult


@tool
def edit_file(path: str, content: str) -> EditFileResult:
    """
    Write UTF-8 content to a file inside the sandbox.
    Creates necessary parent directories automatically.
    Rejects traversals, absolute paths outside the sandbox, symlink escapes,
    and attempts to write to a directory.
    """
    resolved_path = resolve_sandbox_path(path)

    if resolved_path.is_dir():
        raise ValueError(f"Path {path} resolves to a directory, cannot edit file")

    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    encoded_content = content.encode("utf-8")
    resolved_path.write_bytes(encoded_content)

    return EditFileResult(path=path, bytes_written=len(encoded_content))
