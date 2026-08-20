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
PUBLIC_CONCIERGE_SESSION_TTL_ENV = "AGENT_OS_PUBLIC_CONCIERGE_SESSION_TTL_SECONDS"

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
VI_PATTERN = re.compile(
    r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
    re.I,
)
VI_HINTS = {
    "anh",
    "ban",
    "bạn",
    "biet",
    "biết",
    "cần",
    "cho",
    "chao",
    "chào",
    "dich",
    "dịch",
    "giup",
    "giúp",
    "lien",
    "liên",
    "minh",
    "mình",
    "tieng",
    "tiếng",
    "toi",
    "tôi",
}


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
    session_id: str | None = Field(default=None, max_length=120)
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
    session_id: str | None = None
    runtime: Literal["agent-os"] = "agent-os"
    harness: Literal["hermes", "deterministic"] = "deterministic"
    model: str | None = None
    fallback: bool = True


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public_concierge_sessions (
                session_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                visitor_id TEXT,
                hermes_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _session_ttl_seconds() -> int:
    try:
        value = int(os.getenv(PUBLIC_CONCIERGE_SESSION_TTL_ENV, "86400"))
    except ValueError:
        return 86400
    return min(604800, max(300, value))


def resolve_public_session(
    profile: PublicConciergeProfile,
    request: PublicChatRequest,
) -> tuple[str, str | None]:
    """Resolve an opaque browser token without exposing Hermes session ids."""
    _init_db()
    now = dt.datetime.now(dt.UTC)
    requested = str(request.session_id or "").strip()
    visitor_id = str(request.visitor_id or "").strip() or None

    with contextlib.closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        cutoff = now - dt.timedelta(seconds=_session_ttl_seconds())
        conn.execute(
            "DELETE FROM public_concierge_sessions WHERE updated_at < ?",
            (cutoff.isoformat(),),
        )
        conn.commit()
        if requested and visitor_id:
            row = conn.execute(
                """
                SELECT session_id, visitor_id, hermes_session_id, updated_at
                FROM public_concierge_sessions
                WHERE session_id = ? AND tenant_id = ?
                """,
                (requested, profile.tenant_id),
            ).fetchone()
            if row is not None and row["visitor_id"] == visitor_id:
                updated_at = dt.datetime.fromisoformat(str(row["updated_at"]))
                if (now - updated_at).total_seconds() <= _session_ttl_seconds():
                    return str(row["session_id"]), row["hermes_session_id"]

        session_id = str(uuid.uuid4())
        timestamp = now.isoformat()
        conn.execute(
            """
            INSERT INTO public_concierge_sessions (
                session_id, tenant_id, visitor_id, hermes_session_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (session_id, profile.tenant_id, visitor_id, timestamp, timestamp),
        )
        conn.commit()
        return session_id, None


def bind_public_hermes_session(
    profile: PublicConciergeProfile,
    session_id: str,
    hermes_session_id: str,
) -> None:
    """Persist the private Hermes id behind its opaque public session token."""
    if not hermes_session_id.strip():
        return
    _init_db()
    with contextlib.closing(_connect()) as conn:
        conn.execute(
            """
            UPDATE public_concierge_sessions
            SET hermes_session_id = ?, updated_at = ?
            WHERE session_id = ? AND tenant_id = ?
            """,
            (
                hermes_session_id.strip(),
                dt.datetime.now(dt.UTC).isoformat(),
                session_id,
                profile.tenant_id,
            ),
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


def _is_vietnamese(message: str) -> bool:
    lowered = message.lower()
    if VI_PATTERN.search(lowered):
        return True
    words = set(
        re.findall(
            r"[a-zA-Zăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]+",
            lowered,
        )
    )
    return bool(words & VI_HINTS)


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
            label = (
                visitor.company or visitor.name or visitor.email or "Website visitor"
            )
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


def _format_bullets(items: list[str], *, limit: int = 5) -> str:
    return "\n".join(f"- {item.strip()}" for item in items[:limit] if item.strip())


def _format_job_fit(profile: PublicConciergeProfile, *, is_vi: bool) -> list[str]:
    if is_vi:
        answer_parts = [
            "Nếu nhìn từ public profile, Simon phù hợp nhất với các vai trò giao giữa growth, GTM, product marketing và commercial execution.",
            "\n".join(
                [
                    "- Growth / GTM / Commercial Growth: biến insight thị trường thành positioning, acquisition system, launch plan và sales enablement.",
                    "- Product Marketing: nối customer insight, value proposition, messaging và go-to-market.",
                    "- Launch / Brand / F&B marketing: phù hợp khi cần vừa chiến lược vừa execution thực tế.",
                    "- AI-enabled operations / AgentOS workflows: thiết kế workflow chatbot internal/external, memory, task routing và automation có guardrails.",
                ]
            ),
        ]
        if profile.proof_points:
            answer_parts.append(
                "Một vài tín hiệu public:\n"
                + _format_bullets(profile.proof_points, limit=4)
            )
        answer_parts.append(
            "Nếu bạn đang tuyển, mình nên biết thêm industry, stage, target market và KPI chính để map fit rõ hơn."
        )
    else:
        answer_parts = [
            "From Simon's public profile, the strongest fit is for roles that sit between growth, GTM, product marketing, and commercial execution.",
            "\n".join(
                [
                    "- Growth / GTM / Commercial Growth: turning market insight into positioning, acquisition systems, launches, and sales enablement.",
                    "- Product Marketing: connecting customer insight, value proposition, messaging, and go-to-market.",
                    "- Launch / Brand / F&B marketing: useful when the role needs strategy plus hands-on execution.",
                    "- AI-enabled operations / AgentOS workflows: designing guarded internal or external assistant workflows.",
                ]
            ),
        ]
        if profile.proof_points:
            answer_parts.append(
                "Public signals:\n" + _format_bullets(profile.proof_points, limit=4)
            )
        answer_parts.append(
            "If you're hiring, share the industry, stage, market, and success metric, and I can map the fit more clearly."
        )
    return answer_parts


def _format_about_simon(profile: PublicConciergeProfile, *, is_vi: bool) -> list[str]:
    if is_vi:
        answer_parts = [
            profile.summary,
            "Nói ngắn gọn: Simon làm ở vùng growth / GTM / product marketing / commercial growth, và đang thử nghiệm AgentOS-style workflows để biến AI thành operating system thực dụng.",
        ]
        if profile.services:
            answer_parts.append(
                "Các mảng public có thể hỏi thêm:\n"
                + _format_bullets(profile.services, limit=5)
            )
    else:
        answer_parts = [
            profile.summary,
            "In short: Simon works around growth, GTM, product marketing, and commercial growth, with practical AgentOS-style workflows for AI-enabled operating systems.",
        ]
        if profile.services:
            answer_parts.append(
                "Public areas you can ask about:\n"
                + _format_bullets(profile.services, limit=5)
            )
    return answer_parts


class PublicConcierge:
    def __init__(self, profile: PublicConciergeProfile):
        self.profile = profile

    def respond(self, request: PublicChatRequest) -> PublicChatResponse:
        message = request.message.strip()
        is_vi = _is_vietnamese(message)
        answer_parts: list[str]
        citations: list[str]
        links: list[PublicLink] = []

        if _contains_any(
            message,
            {
                "private",
                "memory",
                "task",
                "telegram",
                "file",
                "vault",
                "secret",
                "token",
                "password",
                "riêng tư",
                "nội bộ",
                "mật khẩu",
                "bí mật",
            },
        ):
            answer_parts = [
                "Mình không thể truy cập memory, task, file, chat hoặc tool nội bộ của SimonOS. Mình chỉ dùng thông tin public đã duyệt."
                if is_vi
                else "I cannot access private SimonOS memory, tasks, files, chats, or tools. I only use approved public information.",
            ]
            citations = ["profile.boundaries", "profile.summary"]
        elif _contains_any(
            message,
            {
                "job",
                "jobs",
                "role",
                "roles",
                "position",
                "positions",
                "fit",
                "hiring",
                "career",
                "phù hợp",
                "phu hop",
                "vị trí",
                "vi tri",
                "công việc",
                "cong viec",
                "nghề",
                "nghe",
            },
        ):
            answer_parts = _format_job_fit(self.profile, is_vi=is_vi)
            citations = ["profile.summary", "profile.services", "profile.proof_points"]
        elif _contains_any(
            message,
            {
                "simon",
                "who is",
                "about",
                "bio",
                "background",
                "profile",
                "là ai",
                "la ai",
                "hỏi simon",
                "hoi simon",
                "về simon",
                "ve simon",
            },
        ):
            answer_parts = _format_about_simon(self.profile, is_vi=is_vi)
            citations = ["profile.summary", "profile.services"]
        elif _contains_any(
            message,
            {
                "service",
                "services",
                "offer",
                "help",
                "hire",
                "dịch vụ",
                "giúp",
                "cần",
                "tuyển",
            },
        ):
            if is_vi:
                answer_parts = [
                    "Mình là Simos - Simon's associate. Mình có thể giúp bạn xem nhanh Simon có phù hợp cho growth, GTM, launch hoặc workflow AI không.",
                ]
            else:
                answer_parts = [
                    "Hey, I'm Simos - Simon's associate. I can help you quickly see whether Simon is relevant for growth, GTM, launches, or AI-enabled workflows.",
                ]
            if self.profile.services:
                label = (
                    "Một vài mảng Simon có thể hỗ trợ:" if is_vi else "Useful areas:"
                )
                answer_parts.append(
                    label + "\n" + _format_bullets(self.profile.services)
                )
            citations = ["profile.summary", "profile.services"]
        elif _contains_any(
            message,
            {
                "project",
                "work",
                "case",
                "portfolio",
                "dự án",
                "du an",
                "kinh nghiệm",
            },
        ):
            intro = (
                "Một vài ví dụ public bạn có thể xem qua:"
                if is_vi
                else "A few public examples you can skim:"
            )
            answer_parts = [intro]
            if self.profile.projects:
                answer_parts.append(_format_bullets(self.profile.projects, limit=4))
            if self.profile.proof_points:
                label = "Tín hiệu public:" if is_vi else "Public signals:"
                answer_parts.append(
                    label + "\n" + _format_bullets(self.profile.proof_points, limit=4)
                )
            citations = ["profile.summary", "profile.projects", "profile.proof_points"]
        elif _contains_any(
            message,
            {
                "cv",
                "resume",
                "linkedin",
                "email",
                "contact",
                "whatsapp",
                "zalo",
                "liên hệ",
                "lien he",
            },
        ):
            answer_parts = [
                "Bạn có thể liên hệ Simon qua các kênh public bên dưới."
                if is_vi
                else "You can reach Simon through the public links below."
            ]
            links = self.profile.links
            citations = ["profile.links"]
        else:
            if is_vi:
                answer_parts = [
                    "Chào bạn, mình là Simos - Simon's associate.",
                    "Mình có thể trả lời nhanh bằng tiếng Việt hoặc tiếng Anh về dịch vụ, work examples, CV và cách liên hệ Simon.",
                ]
            else:
                answer_parts = [
                    self.profile.welcome,
                    "I can answer in English or Vietnamese about services, public work, CVs, and contact paths.",
                ]
            citations = ["profile.welcome", "profile.summary"]

        lead = None
        lead_summary = _lead_summary(request)
        if lead_summary is not None:
            lead = _record_lead(self.profile, request, lead_summary)
            answer_parts.append(
                "Mình đã lưu lại để Simon review trước khi follow-up."
                if is_vi
                else "Got it. I saved this for Simon to review before any follow-up."
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
