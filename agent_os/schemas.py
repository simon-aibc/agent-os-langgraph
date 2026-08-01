from pydantic import BaseModel


class ArchitectBrief(BaseModel):
    files: list[str]
    changes: list[str]
    verify_cmd: str


class ReadFileResult(BaseModel):
    path: str
    content: str


class GrepMatch(BaseModel):
    path: str
    line: int
    text: str


class GrepResult(BaseModel):
    matches: list[GrepMatch]


class ExecutorReport(BaseModel):
    diff: str
    verify_output: str
    success: bool


class EditFileResult(BaseModel):
    path: str
    bytes_written: int


class BashResult(BaseModel):
    args: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
