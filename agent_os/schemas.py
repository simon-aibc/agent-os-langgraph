from pydantic import BaseModel, Field


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
    truncated: bool = False


class RouterDecision(BaseModel):
    """Output of the router LLM classifying the user's intent."""

    tool: str | None
    confidence: float = Field(..., ge=0.0, le=1.0)
    arguments: dict[str, object] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    """Output of executing a native tool."""

    tool: str
    output: str
    success: bool
