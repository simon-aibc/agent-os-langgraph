# Roadmap

Vision: **A generic multi-agent OS that can serve as a personal daily driver
without leaking any personal data into the public repository.**

The v1.0 release proves the framework end-to-end. The roadmap below closes the
gaps between "portfolio artifact" and "daily driver replacement" for anyone
running a bespoke agent stack on top of subscription-tied CLI tools.

## Guiding principle: framework public, config private

The public repository is a generic framework. Personal usage layers on top via
environment variables, gitignored directories, and — optionally — a separate
private repository that imports this one as a dependency.

```
┌─────────────────────────────────────────────┐
│ PUBLIC   agent_os/     framework            │
│          docs/         PRD, architecture    │
│          skills/       generic examples     │
│          .env.example  placeholders         │
└─────────────────────────────────────────────┘
                    ↑ injection points
┌─────────────────────────────────────────────┐
│ PRIVATE  .env                real secrets   │
│          skills_private/     personal       │
│          vault_bridge_path   in .env only   │
│          checkpoints.db      gitignored     │
└─────────────────────────────────────────────┘
```

## Current state — v1.0

Shipped 2026-08-02 (tag `v1.0.0`):

- Typed `SimonState` + compiled StateGraph
- Conditional supervisor with 7-priority routing
- Three-tier cascading tool dispatcher (deterministic → cheap LLM → escalate)
- Read-only architect sub-graph with structured `ArchitectBrief`
- Sandboxed executor sub-graph with `shell=False`, path/symlink escape checks
- Interrupt-driven human plan gate with normalized feedback
- SQLite checkpoints, cross-process resume proven
- MCP integrations: filesystem, codegraph, gbrain — with credential-safe loading
- Rich streaming CLI, credential redaction, offline startup
- Portfolio docs, GitHub Actions CI (Python 3.11+3.12), Ruff, 199 tests

## Milestones

Effort estimates assume the same architect+executor delegation pattern used to
ship v1.0.

### v1.1 — Subscription LLM backends (~2 days)

Custom `BaseChatModel` adapters that wrap OAuth-authenticated CLI tools.
Removes API billing for anyone with a Claude Code Max or ChatGPT Plus
subscription. Structured output via JSON-mode prompting; streaming becomes
batch (documented trade-off).

- `agent_os/llm_cli.py` with `ClaudeCodeCliChatModel` and `CodexCliChatModel`
- `.env` accepts `LLM_ARCHITECT=cli/claude-code`, `LLM_EXECUTOR=cli/codex`
- README section: "Runs on subscription CLI tools without API billing"

### v1.2 — Pluggable skills system (~3 days)

Skills as folders with a `SKILL.md` frontmatter + optional `handler.py`.
Framework loads from `skills/` (public) plus every path in
`AGENT_OS_SKILL_DIRS`. Personal skills live outside the repo or in an
explicitly gitignored directory.

- Skill loader, registration into `SkillRegistry`
- Two example skills in the public repo
- Documentation for the frontmatter schema and handler contract

### v1.3 — Vault memory adapter (~3 days)

Vault content stays on disk and never enters git. A `VaultReader` exposes
search + read via the existing gbrain MCP; a `VaultWriter` appends logs and
creates decisions through the human gate.

- `agent_os/vault.py` — reader/writer with `AGENT_OS_VAULT_PATH` env
- Hot context and standards inject into architect system prompt on start
- All vault writes routed through the approval gate

### v1.4 — Personal context system (~2 days)

User profile and durable memory injected into every session.

- Templates for `MEMORY.md`, `user.md`, `standards.md`
- Session initializer loads the user profile into state
- Prompt prefixes composed from public defaults + private overrides

### v1.5 — Interactive REPL and TUI (~2 days)

Textual-based console for daily driving.

- `agent-os chat` — persistent REPL with a session pane, an event pane, and
  a keyboard-driven HITL panel
- `agent-os sessions ls|resume|rm`
- One-shot `agent-os "task"` mode preserved

### v2.0 — Ambient interfaces

The pieces that turn the daily driver into an OS. Each sub-milestone ships
independently.

- **v2.0a** Telegram bot interface (light-ops door, HITL via inline buttons)
- **v2.0b** Cron/launchd wrapper with YAML schedule config and isolated
  session logs
- **v2.0c** Read-only dashboard (Streamlit or lightweight FastAPI + HTMX)
- **v2.0d** WhatsApp / Slack adapters (optional, mirror Telegram pattern)

### v2.1 — Full parity + retirement path

- Port bespoke workflows (deploy runbooks, batch pipelines)
- Migration guide for existing Hermes-style setups
- Two-week dogfood window before retiring the previous system

## Safety principles for public + private hybrid

The framework is designed to be safe to publish while running privately.

### 1. Hard `.gitignore` from day one

```
.env
.env.*
secrets/
skills_private/
checkpoints.db*
sandbox/
logs/
*.token
credentials.json
```

### 2. Secret scanning in CI

Add `gitleaks` (or equivalent) to the CI workflow so leaked credentials fail
the build.

### 3. Config schema in public, values in private

`.env.example` and docs describe every environment variable, but only with
placeholder values. Real values live in the user's local `.env`.

### 4. No personal data in tests

Tests use `tmp_path`, `alice/bob`, `example.com`. Fixtures are ephemeral.

### 5. Vault stays local

Vault path is read from `AGENT_OS_VAULT_PATH`; nothing in the repository
depends on a specific vault layout. Vault content is never committed under any
circumstance.

### 6. Session state gitignored

`checkpoints.db` and any `logs/` are private by default because they contain
task text, plans, tool results, and file content.

### 7. Credential redaction (shipped in v1.0)

CLI tool arguments and results redact common credential keys before display.
Every new integration extends the redaction list.

### 8. Approval gate on all writes to sensitive state

Vault writes, non-sandbox filesystem writes, and any integration action with
outbound side effects pass through `human_gate` by default.

### 9. Branch protection on the public repo

Main is protected; PRs must pass CI; force-push is disabled.

## Ordering by return-on-effort

1. **v1.1** — subscription LLM backends → unlocks $0 daily driver
2. **v1.3** — vault adapter → unlocks memory continuity
3. **v1.2** — skills system → unlocks personal workflows
4. **v1.5** — REPL/TUI → unlocks daily UX
5. **v2.0a** — Telegram → unlocks mobile ambient
6. **v2.0b** — cron → unlocks autonomous tasks
7. **v1.4** — personal context refinement
8. **v2.0c**, **v2.1** — polish and retirement

Total: ~30–40 engineering-days delivered as small, mergeable milestones.
