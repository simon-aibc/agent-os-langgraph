# Roadmap

Vision: **a generic, local-first multi-agent orchestrator that can grow from a
portfolio-quality coding workflow into a personal daily driver without putting
private context in the public repository.**

## Current state — v1.1.2

Released 2026-08-03:

- typed LangGraph state and explicit supervisor routing;
- three-tier dispatcher with a `0.80` structured-routing threshold;
- read-only architect, human plan gate, and sandbox-scoped executor;
- SQLite checkpoints with cross-process and mid-run resume;
- native tools plus optional filesystem, CodeGraph, and HTTP MCP adapters;
- streamed CLI output, stable exit codes, and checkpoint-aware interruption;
- token trimming, prompt caching, retries, and retained-output caps;
- Claude Code and Codex subscription CLI delegators;
- strict Codex JSON schemas and actionable CLI authentication failures;
- 263 offline tests plus opt-in external integration tests.

See [`CHANGELOG.md`](../CHANGELOG.md) for shipped patch details.

## Public/private boundary

The public repository contains the framework, generic documentation, example
configuration, and tests. Private deployments supply credentials, checkpoints,
sandbox content, personal skills, and memory through ignored files or external
paths.

```text
PUBLIC                         PRIVATE / LOCAL
agent_os/ framework            .env credentials
docs/ specifications           checkpoints.db workflow state
tests/ generic fixtures        sandbox/ working files
.env.example placeholders      external skills and vault data
```

## Planned milestones

### v1.2 — Pluggable skill packages

- Load skills from package folders with documented metadata and handler
  contracts.
- Support multiple `AGENT_OS_SKILL_DIRS` outside the repository.
- Ship generic example skills and collision diagnostics.
- Keep personal workflow implementations private by default.

### v1.3 — Vault memory adapter

- Read a vault path from configuration without assuming a private layout.
- Inject bounded hot context at architect boundaries.
- Route vault mutations through an explicit approval policy.
- Add provenance and retention controls for persisted context.

### v1.4 — User context profiles

- Compose public prompt defaults with private user and standards files.
- Define size limits and precedence rules for injected context.
- Add redacted diagnostics showing which context sources were loaded.

### v1.5 — Interactive REPL and TUI

- Persistent `agent-os chat` sessions.
- Session list, resume, inspect, and delete commands.
- Dedicated event and HITL panels while preserving one-shot CLI mode.

### v2.0 — Ambient interfaces

- Telegram interface with explicit approval callbacks.
- Scheduler with isolated thread IDs and execution logs.
- Read-only workflow dashboard.
- Optional collaboration adapters after the security model is proven.

### v2.1 — Deployment and migration

- Container or microVM execution profile for untrusted workloads.
- Deployment guide and operational health checks.
- Migration guidance for bespoke agent stacks.
- Sustained dogfood window before replacing an existing daily driver.

## Backlog informed by v1 dogfood

- Add delegator adapters only for CLIs with stable noninteractive output and
  enforceable permission modes. Hermes and Antigravity are not supported yet.
- Stream subprocess output before retention caps to reduce peak memory.
- Add process, network, and resource isolation outside the Python path sandbox.
- Add durable, process-safe budget accounting for API-backed models.
- Record and embed an end-to-end terminal demo.
- Publish a deployment recipe only after a clean-machine installation test.

## Repository hardening

Shipped:

- GitHub secret scanning and push protection;
- offline CI on Python 3.11 and 3.12;
- warnings-as-errors and Ruff;
- ignored credentials, checkpoints, sandboxes, logs, and local artifacts.

Maintained through GitHub settings:

- protected `main` branch with required CI checks;
- automated dependency security updates;
- release notes attached to version tags.

## Ordering by return on effort

1. v1.2 skill packages — unlock reusable workflows.
2. v1.3 vault adapter — unlock continuity.
3. v1.5 REPL/TUI — improve daily interaction.
4. v1.4 context profiles — deepen personalization after boundaries are proven.
5. v2.0 ambient interfaces — add mobile and scheduled entry points.
6. v2.1 deployment — harden for broader use.

Milestones remain small and independently reviewable. Public features must not
require or reveal a particular user's private vault, credentials, or workflows.
