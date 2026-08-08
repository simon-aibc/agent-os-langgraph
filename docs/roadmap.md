# Roadmap

Vision: **an open-source, local-first backbone for building durable, controllable AI agent systems — generic primitives an engineering team can clone, audit, extend, and self-host, without private context living in the public repository.**

## Current state — v1.5.0

Released up through v1.5.0, plus merged unreleased features:
- Morning brief engine
- Context spine
- Serve API (FastAPI, localhost-first)

See [`CHANGELOG.md`](../CHANGELOG.md) for shipped patch details.

## Public/private boundary

The public repository contains the framework, generic documentation, example configuration, and tests. Private deployments supply credentials, checkpoints, sandbox content, personal skills, and memory through ignored files or external paths.

See [ADR 0001: Public vs Private](adr/0001-public-vs-private.md) for boundary decisions.

## Direction: North Stars

1. **Backbone quality:** Durable, controllable, and observable foundations.
2. **Dogfood validation:** Building tools we actually use daily.
3. **External legibility:** Clear boundaries and extension points for the community.

## Planned milestones

### v1.6 — Workspace + Policy foundation
- Enhance context boundaries and establish policy-driven execution rules.

### v1.7 — Run Ledger + Runtime API + Operator Console
- Expose structured runtime interfaces for external orchestrators and interactive operator consoles.

### v1.8 — Scheduler + self-host
- Add robust background scheduling and simplify self-hosted deployments.

### v2.0 — Stable extension API
- Finalize interfaces for native skills, memory connectors, and backend adapters.

## Repository hardening

Maintained through GitHub settings:
- protected `main` branch with required CI checks;
- automated dependency security updates;
- release notes attached to version tags.
