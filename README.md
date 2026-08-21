# Agent OS

[![CI](https://github.com/simon-aibc/agent-os-langgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/simon-aibc/agent-os-langgraph/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.11-3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)
[![Release](https://img.shields.io/badge/release-v2.4.0-green.svg)](https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v2.4.0)
[![Typed](https://img.shields.io/badge/types-py.typed-informational.svg)](agent_os/api)

> **Agent OS: Everything is a Plugin.**<br>
> An open-source, local-first Operating System and extensible harness for autonomous AI agents.

Agent OS is an auditable, self-hostable agent operating system providing deterministic fast-path execution, read-only architect planning, human approval governance, immutable policy floors, memory retrieval lifecycles, anti-SSRF signed event egress, and a modular plugin runtime. Under the hood, stateful graph execution and checkpointing are powered by LangGraph.

**Current release:** [v2.4.0](https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v2.4.0) |
[Changelog](CHANGELOG.md) |
[Architecture](docs/architecture.md) |
[Extending Agent OS](docs/EXTENDING.md) |
[Self-Hosting](docs/self-hosting.md) |
[Product Spec](docs/PRD.md) |
[Roadmap](docs/roadmap.md)

---

## Table of Contents

1. [Core OS Primitives](#core-os-primitives)
2. [Everything is a Plugin](#everything-is-a-plugin)
3. [Quickstart](#quickstart)
4. [Usage & Operating Modes](#usage--operating-modes)
5. [Self-Hosting & Operations](#self-hosting--operations)
6. [Extension Conformance Kit](#extension-conformance-kit)
7. [Security & Governance Invariants](#security--governance-invariants)
8. [Development & Contributing](#development--contributing)
9. [License](#license)

---

## Core OS Primitives

Agent OS organizes autonomous agent operations into distinct operating system subsystems:

- **Kernel / Deterministic Fast-Path**: Exact, low-risk tool operations execute immediately with zero model latency and zero token cost.
- **Architect & Planning Subsystem**: Ambiguous or high-complexity tasks escalate to a read-only architect that produces structured execution proposals.
- **Governance & Policy Floor**: Side-effect proposals require approval; non-bypassable policy floors enforce strict security constraints regardless of policy mode.
- **Process Isolation & Sandbox Execution**: Side effects execute strictly within configured workspace sandbox boundaries.
- **Memory & Retrieval Subsystem**: Multi-vault connectors (Markdown, G-Brain, SQLite, vectors) with cold-start indexing lifecycles (`IndexableMemory`) and non-blocking context injection (`ContextProvider`).
- **Persistence & Audit Subsystem**: SQLite state stores with live additive migrations, WAL-checkpoint backups, strategy assignment audit traces, and actor provenance (`Principal`).
- **IPC & Event Egress**: Real-time Server-Sent Events (SSE), local cron/interval scheduling, and DNS-rebinding-safe HMAC-signed webhooks (`EventSink`).

```mermaid
flowchart TD
    START(["User Request"]) --> planner["Planner (Context Injection & Retrieval)"]
    planner --> supervisor["Supervisor Engine"]
    supervisor -->|"deterministic fast-path"| dispatcher["Tool Dispatcher (Kernel Mode)"]
    dispatcher -->|"success"| END(["Task Complete"])
    dispatcher -->|"complex / ambiguous"| supervisor
    supervisor -->|"escalate"| architect["Architect (Read-Only Planning)"]
    architect --> gate["Human Gate (Immutable Policy Floor)"]
    gate -->|"approved"| supervisor
    gate -->|"rejected"| architect
    supervisor -->|"execute"| executor["Executor (Sandbox Scoped)"]
    executor --> supervisor
    supervisor -->|"complete"| END
```

---

## Everything is a Plugin

Agent OS exposes a frozen, identity-preserving public facade under `agent_os.api` with 7 standard plugin entry-point groups:

| Plugin Group | Protocol / Contract | Description |
|---|---|---|
| `agent_os.connectors` | `Connector` | Custom action tools, CLI integrations, and external API connectors |
| `agent_os.memory_connectors` | `MemoryConnector`, `WritableMemory`, `IndexableMemory` | Long-term memory vaults, knowledge bases, and vector storage |
| `agent_os.backends` | `BackendAdapter` | Model execution backends (Claude Code, Codex CLI, LiteLLM, Ollama) |
| `agent_os.policies` | `PolicyEngine` | Custom policy evaluators, role constraints, and governance rules |
| `agent_os.skill_packages` | `SkillPackageLoader` | Reusable skill bundles, domain workflows, and instruction sets |
| `agent_os.context_providers` | `ContextProvider` | Pre-planner retrieval hooks and dynamic context injection |
| `agent_os.event_sinks` | `EventSink` | Lifecycle run event egress, telemetry, and signed webhook sinks |

### Authoring an Agent OS Plugin

Third-party extensions build directly against `agent_os.api` without private internals:

```python
from agent_os.api import (
    Connector,
    ContextProvider,
    ContextBlock,
    EventSink,
    IndexableMemory,
    MemoryConnector,
    PluginRegistry,
    Principal,
    SUPPORTED_SIDE_EFFECTS,
)

class MyCustomConnector:
    name = "my_tool"

    def capabilities(self) -> list[str]:
        return ["custom_action"]

    def describe_side_effect(self, action: str, arguments: dict) -> str:
        return "read"

    def invoke(self, action: str, arguments: dict) -> dict:
        return {"status": "ok"}
```

---

## Quickstart

### Prerequisites

- Python 3.11 or 3.12
- Git
- Docker with Compose v2 (optional, for self-hosted container deployment)

### 1. Installation

```bash
git clone https://github.com/simon-aibc/agent-os-langgraph.git
cd agent-os-langgraph

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,serve]"
```

### 2. Zero-LLM Fast-Path Execution

Execute deterministic operations directly through the kernel fast-path:

```bash
agent-os "read_file README.md" --thread-id quickstart --sandbox .
```

Output:
```text
[THREAD] quickstart
[SUPERVISOR] -> tool_dispatcher
[TOOL] read_file({"path": "README.md"})
[RESULT] # Agent OS ...
```

### 3. Configure Model Roles

```bash
cp .env.example .env
```

Agent OS reads 3 decoupled roles:

```bash
LLM_ROUTER="ollama/qwen2.5:14b"
LLM_ARCHITECT="anthropic/claude-opus-4-8"
LLM_EXECUTOR="openai/gpt-5.5"
```

Subscription CLIs are also supported out of the box:

```bash
LLM_ARCHITECT=cli/claude-code
LLM_EXECUTOR=cli/codex
```

---

## Usage & Operating Modes

### Architect Planning & Approval Gates

When tasks require file modifications, code creation, or complex workflows, Agent OS builds a formal proposal and waits for approval:

```bash
agent-os "add type annotations to math_util.py and run tests" \
  --thread-id type-check-task \
  --sandbox ./sandbox
```

At the approval prompt, choose `approved` (one-time), `session`, `always_approve` (learned rule), or `rejected: <reason>`.

Interrupted runs resume seamlessly from SQLite checkpoints:

```bash
agent-os --resume --thread-id type-check-task --sandbox ./sandbox
```

### Multi-Turn Chat, Sessions & Schedules

```bash
# Interactive multi-turn CLI session
agent-os chat --thread-id dev-session

# Inspect active sessions and audit trails
agent-os sessions list
agent-os sessions inspect dev-session

# Local cron and interval background schedules
agent-os schedule list
```

### Self-Update & Live Migrations

```bash
# Check latest updates against GitHub releases
agent-os update --check

# Upgrade runtime with pre-migration database backup and daemon restart
agent-os update --yes --reload
```

---

## Self-Hosting & Operations

### Run with Docker Compose

Start the complete Agent OS backend and Web Operator Console:

```bash
docker compose up -d
```

- **Agent OS Runtime API**: `http://127.0.0.1:4680`
- **Operator Console**: `http://127.0.0.1:3000`
- **Health Check**: `http://127.0.0.1:4680/api/health`

### Run Runtime Server Locally

```bash
agent-os serve --host 127.0.0.1 --port 4680
```

Core Runtime Endpoints:
- `GET /api/health` — Runtime health and update cache
- `POST /api/runs` — Trigger non-blocking asynchronous agent runs
- `GET /api/runs/events` — Server-Sent Events (SSE) stream for live execution logs
- `POST /api/runs/{run_id}/approve` — Submit gate decisions for suspended runs

---

## Extension Conformance Kit

Agent OS includes a lightweight testing kit under `agent_os.testing.conformance` to validate plugins in standalone CI:

```python
from agent_os.testing.conformance import (
    check_connector,
    check_memory_connector,
    check_context_provider,
    check_event_sink,
)

def test_custom_plugin_conformance():
    sink = MyCustomEventSink()
    check_event_sink(sink)
```

Run the complete test suite:

```bash
pytest -q
```

---

## Security & Governance Invariants

- **Non-Bypassable Policy Floors**: Hard safety constraints (e.g. `payment` or `privileged` actions) cannot be bypassed by plugins, even with `mode="off"`.
- **Anti-SSRF DNS-Rebinding Protection**: Webhooks validate target IPs against loopback/private CIDRs, pin sockets to verified IPs, and preserve TLS SNI/certificate validation.
- **Server-Trusted Actor Identity**: `Principal` provenance is resolved server-side to prevent header spoofing in multi-tenant environments.
- **Workspace Isolation**: Database files, permission rules, and observation records are isolated per workspace path.

---

## Development & Contributing

- [CONTRIBUTING.md](CONTRIBUTING.md) — Contributing guidelines and development workflow.
- [docs/EXTENDING.md](docs/EXTENDING.md) — Comprehensive guide to developing Agent OS plugins.
- [docs/architecture.md](docs/architecture.md) — Deep-dive system architecture.

---

## License

[MIT](LICENSE) © Simon Tran
