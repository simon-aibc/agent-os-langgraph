# Public concierge facade

Agent OS can expose a narrow public website-chat facade for external visitors.
The facade is intentionally separate from private Agent OS workspaces: it uses
only an approved public profile, deterministic routing, a small lead ledger,
and rate limiting. It does not call private memory connectors, tools, files,
Telegram bots, or executor backends.

## Boundary

Use this facade for:

- answering basic public questions about a company, person, service, or project;
- linking to approved public contact channels and documents;
- capturing visitor contact details as review-required leads;
- demonstrating how an enterprise can attach an external chatbot to Agent OS
  without exposing its internal assistant.

Do not use it for:

- direct access to private vaults, chats, tasks, schedules, files, or shell;
- autonomous outbound email, WhatsApp, Telegram, payment, or CRM mutation;
- publishing unreviewed claims, pricing, client data, metrics, or private
  operating context.

## Configuration

The endpoint is disabled by default. Set one of these variables before starting
`agent-os serve`:

```bash
AGENT_OS_PUBLIC_CONCIERGE_PATH="./public-concierge.json"
# or
AGENT_OS_PUBLIC_CONCIERGE_JSON='{"tenant_id":"acme", ...}'
```

Example profile:

```json
{
  "tenant_id": "acme",
  "assistant_name": "Acme Concierge",
  "welcome": "Hi, I can answer from Acme's approved public profile.",
  "summary": "Acme helps teams connect market insight to GTM execution.",
  "services": ["positioning", "launch planning", "sales enablement"],
  "projects": ["Project Atlas", "Project Delta"],
  "proof_points": ["12 public case studies"],
  "links": [
    {
      "label": "Email",
      "url": "mailto:hello@example.com",
      "kind": "email"
    }
  ],
  "suggestions": ["Ask about services", "Ask about public work"]
}
```

For a website integration, also set CORS to the exact site origins:

```bash
AGENT_OS_CORS_ORIGINS="https://example.com,https://uat.example.com"
```

## Endpoints

`POST /api/public/concierge/chat`

Request:

```json
{
  "message": "Can you help with launch planning?",
  "visitor_id": "browser-session-id",
  "source_url": "https://example.com/#contact",
  "visitor": {
    "name": "Ada",
    "email": "ada@example.com",
    "company": "Lovelace Labs",
    "need": "launch planning"
  }
}
```

Response:

```json
{
  "tenant_id": "acme",
  "assistant_name": "Acme Concierge",
  "answer": "Acme helps teams connect market insight to GTM execution.",
  "suggestions": ["Ask about services", "Ask about public work"],
  "links": [],
  "citations": ["profile.summary", "profile.services"],
  "handoff_status": "review_required",
  "lead": {
    "lead_id": "uuid",
    "status": "review_required",
    "summary": "Lovelace Labs: launch planning"
  }
}
```

`GET /api/public/concierge/leads`

Lead review is internal-only. Set `AGENT_OS_PUBLIC_CONCIERGE_ADMIN_TOKEN` and
send either `Authorization: Bearer <token>` or `X-Admin-Token: <token>`.

## Production note

The default self-hosted stack binds to localhost and should not be exposed
directly. Put this route behind a public HTTPS edge with authentication for
admin endpoints, strict CORS, request limits, logging, and a reviewed public
profile. Website chat should talk to this facade, not to the private Agent OS
runtime or any personal assistant endpoint.
