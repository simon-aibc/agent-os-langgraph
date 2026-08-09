"""FastAPI-independent domain input model for schedule creation.

Used by both the CLI and API so validation rules cannot drift.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScheduleInput(BaseModel):
    """Shared, validated input for creating a schedule.

    Enforces the mutual-exclusion and kind-specific payload rules
    specified in the design contract.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    kind: Literal["run", "brief"]
    cron: str | None = None
    every: str | None = None
    timezone: str = "UTC"
    task: str | None = Field(default=None, min_length=1, max_length=4096)
    workspace: str | None = None

    @field_validator("name", "task", mode="after")
    @classmethod
    def _strip_and_check_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("String cannot be empty or only whitespace")
        return v

    @model_validator(mode="after")
    def _cross_field_rules(self) -> ScheduleInput:
        # Exactly one of cron/every.
        if self.cron and self.every:
            raise ValueError("Specify exactly one of 'cron' and 'every', not both")
        if not self.cron and not self.every:
            raise ValueError("Specify exactly one of 'cron' and 'every'")

        # Kind-specific payload validation.
        if self.kind == "run":
            if not self.task:
                raise ValueError("kind=run requires 'task'")
        elif self.kind == "brief":
            if self.task:
                raise ValueError("kind=brief does not accept 'task'")
            if self.workspace:
                raise ValueError("kind=brief does not accept 'workspace'")

        return self

    @property
    def trigger_kind(self) -> Literal["cron", "interval"]:
        return "cron" if self.cron else "interval"

    @property
    def trigger_value(self) -> str:
        return self.cron or self.every or ""

    @property
    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.task:
            result["task"] = self.task
        if self.workspace:
            result["workspace"] = self.workspace
        return result
