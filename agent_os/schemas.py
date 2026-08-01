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
