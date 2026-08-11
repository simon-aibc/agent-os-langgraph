from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB

PUBLIC_CONCIERGE_JSON_ENV = "AGENT_OS_PUBLIC_CONCIERGE_JSON"
PUBLIC_CONCIERGE_PATH_ENV = "AGENT_OS_PUBLIC_CONCIERGE_PATH"
PUBLIC_CONCIERGE_DB_ENV = "AGENT_OS_PUBLIC_CONCIERGE_DB"

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


class PublicLink(BaseModel):
    label: str
    url: str
    kind: str = "link"


class PublicVisitor(BaseModel):
    name: str | None = None
    email: str | None = None
    company: str | None = None
    contact: str | None = None
    need: str | None = None


class PublicConciergeProfile(BaseModel):
    tenant_id: str
    assistant_name: str = "Public Concierge"
    welcome: str
    summary: str
    services: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    links: list[PublicLink] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(
        default_factory=lambda: [
            "I can only use approved public information.",
            "I cannot access private memory, tasks, files, chats, or tools.",
        ]
    )

    @field_validator("tenant_id")
    @classmethod
    def tenant_id_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("tenant_id is required")
        return cleaned


class PublicChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    visitor_id: str | None = Field(default=None, max_length=120)
    visitor: PublicVisitor | None = None
    source_url: str | None = Field(default=None, max_length=500)


class PublicLead(BaseModel):
    lead_id: str
    status: Literal["review_required"]
    summary: str


class PublicChatResponse(BaseModel):
    tenant_id: str
    assistant_name: str
    answer: str
    suggestions: list[str]
    links: list[PublicLink]
    citations: list[str]
    handoff_status: Literal["none", "review_required"]
    lead: PublicLead | None = None


def _default_db_path() -> str:
    checkpoint_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
    if checkpoint_path == ":memory:":
        return checkpoint_path
    root, ext = os.path.splitext(checkpoint_path)
    return f"{root}.public_concierge{ext or '.db'}"


def _db_path() -> str:
    return os.getenv(PUBLIC_CONCIERGE_DB_ENV) or _default_db_path()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _init_db() -> None:
    with contextlib.closing(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public_concierge_leads (
                lead_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                visitor_id TEXT,
                message TEXT NOT NULL,
                visitor_json TEXT NOT NULL,
                source_url TEXT,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def load_public_concierge_profile() -> PublicConciergeProfile | None:
    raw = os.getenv(PUBLIC_CONCIERGE_JSON_ENV, "").strip()
    if raw:
        return PublicConciergeProfile.model_validate_json(raw)

    path = os.getenv(PUBLIC_CONCIERGE_PATH_ENV, "").strip()
    if path:
        payload = Path(path).read_text(encoding="utf-8")
        return PublicConciergeProfile.model_validate_json(payload)

    return None


def list_public_leads(limit: int = 100) -> list[dict[str, object]]:
    _init_db()
    with contextlib.closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT *
            FROM public_concierge_leads
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows: list[dict[str, object]] = []
        for row in cursor.fetchall():
            item = dict(row)
            item["visitor"] = json.loads(str(item.pop("visitor_json")))
            rows.append(item)
        return rows


def _record_lead(
    profile: PublicConciergeProfile,
    request: PublicChatRequest,
    summary: str,
) -> PublicLead:
    _init_db()
    lead_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC).isoformat()
    visitor = request.visitor.model_dump() if request.visitor else {}
    with contextlib.closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO public_concierge_leads (
                lead_id, tenant_id, visitor_id, message, visitor_json, source_url,
                summary, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                profile.tenant_id,
                request.visitor_id,
                request.message,
                json.dumps(visitor, sort_keys=True),
                request.source_url,
                summary,
                "review_required",
                now,
            ),
        )
        conn.commit()
    return PublicLead(lead_id=lead_id, status="review_required", summary=summary)


def _contains_any(message: str, needles: set[str]) -> bool:
    lowered = message.lower()
    return any(needle in lowered for needle in needles)


def _lead_summary(request: PublicChatRequest) -> str | None:
    visitor = request.visitor
    if visitor is not None:
        details = [
            visitor.name,
            visitor.email,
            visitor.company,
            visitor.contact,
            visitor.need,
        ]
        if any(value and value.strip() for value in details):
            label = visitor.company or visitor.name or visitor.email or "Website visitor"
            need = visitor.need or request.message
            return f"{label}: {need}".strip()

    email = EMAIL_PATTERN.search(request.message)
    phone = PHONE_PATTERN.search(request.message)
    if email or phone:
        contact = email.group(0) if email else phone.group(0)
        return f"Website visitor left contact: {contact}"
    return None


def _format_list(items: list[str]) -> str:
    return "; ".join(item.strip() for item in items if item.strip())


class PublicConcierge:
    def __init__(self, profile: PublicConciergeProfile):
        self.profile = profile

    def respond(self, request: PublicChatRequest) -> PublicChatResponse:
        message = request.message.strip()
        answer_parts: list[str]
        citations: list[str]
        links: list[PublicLink] = []

        if _contains_any(message, {"service", "services", "offer", "help", "hire"}):
            answer_parts = [self.profile.summary]
            if self.profile.services:
                answer_parts.append("Public services: " + _format_list(self.profile.services))
            citations = ["profile.summary", "profile.services"]
        elif _contains_any(message, {"project", "work", "case", "portfolio"}):
            answer_parts = [self.profile.summary]
            if self.profile.projects:
                answer_parts.append("Public work: " + _format_list(self.profile.projects))
            if self.profile.proof_points:
                answer_parts.append("Public proof points: " + _format_list(self.profile.proof_points))
            citations = ["profile.summary", "profile.projects", "profile.proof_points"]
        elif _contains_any(message, {"cv", "resume", "linkedin", "email", "contact", "whatsapp", "zalo"}):
            answer_parts = [
                "You can use the approved public contact links below."
            ]
            links = self.profile.links
            citations = ["profile.links"]
        elif _contains_any(message, {"private", "memory", "task", "telegram", "file", "vault"}):
            answer_parts = [
                "I cannot access private SimonOS memory, tasks, files, chats, or tools.",
                self.profile.summary,
            ]
            citations = ["profile.boundaries", "profile.summary"]
        else:
            answer_parts = [self.profile.welcome, self.profile.summary]
            citations = ["profile.welcome", "profile.summary"]

        lead = None
        lead_summary = _lead_summary(request)
        if lead_summary is not None:
            lead = _record_lead(self.profile, request, lead_summary)
            answer_parts.append(
                "I saved this as a review-required lead for the internal team."
            )

        return PublicChatResponse(
            tenant_id=self.profile.tenant_id,
            assistant_name=self.profile.assistant_name,
            answer="\n\n".join(part for part in answer_parts if part),
            suggestions=self.profile.suggestions,
            links=links,
            citations=citations,
            handoff_status="review_required" if lead else "none",
            lead=lead,
        )
