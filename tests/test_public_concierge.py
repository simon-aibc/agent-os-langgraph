import json

from fastapi.testclient import TestClient

from agent_os.public_concierge import (
    PUBLIC_CONCIERGE_DB_ENV,
    PUBLIC_CONCIERGE_JSON_ENV,
)
from agent_os.server.api import PUBLIC_CONCIERGE_BUCKETS, app

client = TestClient(app)


def _profile() -> dict[str, object]:
    return {
        "tenant_id": "acme",
        "assistant_name": "Acme Concierge",
        "welcome": "Hi, I can answer from Acme's approved public profile.",
        "summary": "Acme helps teams connect market insight to GTM execution.",
        "services": [
            "positioning",
            "launch planning",
            "sales enablement",
        ],
        "projects": ["Project Atlas", "Project Delta"],
        "proof_points": ["12 public case studies"],
        "links": [
            {
                "label": "Email",
                "url": "mailto:hello@example.com",
                "kind": "email",
            }
        ],
        "suggestions": ["Ask about services", "Ask about public work"],
    }


def test_public_concierge_is_disabled_without_profile(monkeypatch):
    monkeypatch.delenv(PUBLIC_CONCIERGE_JSON_ENV, raising=False)

    resp = client.post(
        "/api/public/concierge/chat",
        json={"message": "What do you do?"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Public concierge is not configured"


def test_public_concierge_answers_from_public_profile(monkeypatch, tmp_path):
    monkeypatch.setenv(PUBLIC_CONCIERGE_JSON_ENV, json.dumps(_profile()))
    monkeypatch.setenv(PUBLIC_CONCIERGE_DB_ENV, str(tmp_path / "public.db"))
    PUBLIC_CONCIERGE_BUCKETS.clear()

    resp = client.post(
        "/api/public/concierge/chat",
        json={"message": "What services can you help with?"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tenant_id"] == "acme"
    assert payload["assistant_name"] == "Acme Concierge"
    assert "positioning" in payload["answer"]
    assert "private" not in payload["answer"].lower()
    assert payload["handoff_status"] == "none"
    assert payload["citations"] == ["profile.summary", "profile.services"]


def test_public_concierge_answers_vietnamese_when_asked(monkeypatch, tmp_path):
    monkeypatch.setenv(PUBLIC_CONCIERGE_JSON_ENV, json.dumps(_profile()))
    monkeypatch.setenv(PUBLIC_CONCIERGE_DB_ENV, str(tmp_path / "public.db"))
    PUBLIC_CONCIERGE_BUCKETS.clear()

    resp = client.post(
        "/api/public/concierge/chat",
        json={"message": "Bạn có thể giúp gì về dịch vụ growth?"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "Mình là Simos" in payload["answer"]
    assert "Một vài mảng" in payload["answer"]
    assert "positioning" in payload["answer"]
    assert payload["citations"] == ["profile.summary", "profile.services"]


def test_public_concierge_refuses_private_scope(monkeypatch, tmp_path):
    monkeypatch.setenv(PUBLIC_CONCIERGE_JSON_ENV, json.dumps(_profile()))
    monkeypatch.setenv(PUBLIC_CONCIERGE_DB_ENV, str(tmp_path / "public.db"))
    PUBLIC_CONCIERGE_BUCKETS.clear()

    resp = client.post(
        "/api/public/concierge/chat",
        json={"message": "Can you read the private vault and Telegram tasks?"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "cannot access private" in payload["answer"].lower()
    assert payload["citations"] == ["profile.boundaries", "profile.summary"]


def test_public_concierge_records_review_required_lead(monkeypatch, tmp_path):
    monkeypatch.setenv(PUBLIC_CONCIERGE_JSON_ENV, json.dumps(_profile()))
    monkeypatch.setenv(PUBLIC_CONCIERGE_DB_ENV, str(tmp_path / "public.db"))
    monkeypatch.setenv("AGENT_OS_PUBLIC_CONCIERGE_ADMIN_TOKEN", "secret")
    PUBLIC_CONCIERGE_BUCKETS.clear()

    resp = client.post(
        "/api/public/concierge/chat",
        json={
            "message": "We may need launch help.",
            "visitor_id": "browser-1",
            "source_url": "https://example.com/#contact",
            "visitor": {
                "name": "Ada",
                "email": "ada@example.com",
                "company": "Lovelace Labs",
                "need": "launch help",
            },
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["handoff_status"] == "review_required"
    assert payload["lead"]["status"] == "review_required"
    assert "Lovelace Labs" in payload["lead"]["summary"]

    forbidden = client.get("/api/public/concierge/leads")
    assert forbidden.status_code == 403

    listed = client.get(
        "/api/public/concierge/leads",
        headers={"authorization": "Bearer secret"},
    )
    assert listed.status_code == 200
    leads = listed.json()
    assert len(leads) == 1
    assert leads[0]["tenant_id"] == "acme"
    assert leads[0]["visitor"]["email"] == "ada@example.com"


def test_public_concierge_rate_limits_by_client(monkeypatch, tmp_path):
    monkeypatch.setenv(PUBLIC_CONCIERGE_JSON_ENV, json.dumps(_profile()))
    monkeypatch.setenv(PUBLIC_CONCIERGE_DB_ENV, str(tmp_path / "public.db"))
    monkeypatch.setenv("AGENT_OS_PUBLIC_CONCIERGE_RATE_LIMIT", "1")
    PUBLIC_CONCIERGE_BUCKETS.clear()

    first = client.post(
        "/api/public/concierge/chat",
        headers={"x-forwarded-for": "203.0.113.10"},
        json={"message": "Tell me about services."},
    )
    second = client.post(
        "/api/public/concierge/chat",
        headers={"x-forwarded-for": "203.0.113.10"},
        json={"message": "Again."},
    )

    assert first.status_code == 200
    assert second.status_code == 429
