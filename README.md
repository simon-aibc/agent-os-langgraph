# Agent OS LangGraph

[![CI](https://github.com/simon-aibc/agent-os-langgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/simon-aibc/agent-os-langgraph/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.11-3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)
![Tests: 586 passing](https://img.shields.io/badge/tests-586%20passing-brightgreen.svg)
[![Release](https://img.shields.io/github/v/release/simon-aibc/agent-os-langgraph)](https://github.com/simon-aibc/agent-os-langgraph/releases/latest)
![Dependencies pinned](https://img.shields.io/badge/dependencies-pinned-informational.svg)

An open-source, local-first backbone for building durable, controllable AI
agent systems with LangGraph. It gives teams a reference architecture for
deterministic tools, read-only architect planning, human approval gates,
sandbox-scoped execution, durable runtime state, stable extension APIs, and
self-hosted operation.

**Current release:** [v2.0.0](https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v2.0.0) |
[Changelog](CHANGELOG.md) |
[Product specification](docs/PRD.md) |
[Architecture](docs/architecture.md) |
[Roadmap](docs/roadmap.md) |
[Self-hosting](docs/self-hosting.md) |
[Extending](docs/EXTENDING.md)

## Table Of Contents

1. [About The Project](#about-the-project)
2. [Built With](#built-with)
3. [Getting Started](#getting-started)
4. [Usage](#usage)
5. [Self-Hosting](#self-hosting)
6. [Extending Agent OS](#extending-agent-os)
7. [Security And Trust Boundaries](#security-and-trust-boundaries)
8. [Roadmap](#roadmap)
9. [Contributing](#contributing)
10. [License](#license)
11. [Contact](#contact)
12. [Acknowledgments](#acknowledgments)

## About The Project

Agent OS LangGraph is not a hosted SaaS, a prompt pack, or a demo that only
works with one developer's private setup. It is a public, auditable framework
for running agent workflows with clear boundaries:

- deterministic tools handle exact, low-risk work first;
- ambiguous work escalates to a read-only architect;
- human review happens before agent-planned side effects;
- executor work is scoped to the configured sandbox;
- SQLite checkpoints, run ledgers, schedules, and event streams make runs
  observable and resumable;
- stable public interfaces live under `agent_os.api`;
- private deployments supply their own memory, tools, credentials, policies,
  prompts, dashboards, and organization-specific behavior.

The core graph looks like this:

```mermaid
flowchart TD
    START(["START"]) --> planner["planner"] --> supervisor["supervisor"]
    supervisor -->|"new task"| dispatcher["tool_dispatcher"]
    dispatcher -->|"tool success"| END(["END"])
    dispatcher -->|"low confidence or failure"| supervisor
    supervisor -->|"escalated"| architect["architect"]
    architect --> gate["human_gate"]
    gate -->|"approved or rejected"| supervisor
    supervisor -->|"approved"| executor["executor"]
    supervisor -->|"rejected"| architect
    executor --> supervisor
    supervisor -->|"execution complete"| END
```

### What v2.0.0 Demonstrates

| Area | Capability | Why it matters |
|---|---|---|
| Runtime | Runtime API, run ledger, SSE event stream, approve/cancel | External dashboards and operators can observe and control runs |
| Persistence | SQLite checkpoints, separate run/scheduler databases | Work survives restarts without cross-locking the graph checkpointer |
| Control | Architect, human gate, policy engine, executor boundary | Agent-planned side effects are reviewable and auditable |
| Memory | Connector framework, gated write path, hot context | Private memory can be attached without committing private data |
| Scheduling | Local cron/interval schedules for runs and briefs | Long-running self-hosted instances can fire background work |
| Self-hosting | Docker Compose backend + digest-pinned console image | A fresh clone can run the runtime and operator console locally |
| Extensions | Stable `agent_os.api`, `py.typed`, conformance tests | Community users can build connectors, skills, backends, and policies |

### Public vs Private Boundary

The public repository contains generic primitives, contracts, reference
implementations, documentation, and tests. Private deployments should keep the
following outside the public repo:

- `.env` files, API keys, OAuth tokens, and provider credentials;
- checkpoints, run ledgers, schedules, logs, and sandbox output;
- personal vaults, client memory, proprietary prompts, and private skills;
- organization-specific dashboards, Telegram bots, and deployment secrets.

See [ADR 0001: Public vs Private](docs/adr/0001-public-vs-private.md) for the
boundary decision.

## Built With

- [LangGraph](https://github.com/langchain-ai/langgraph) for graph execution,
  interrupts, and checkpointed workflows
- [LangChain](https://github.com/langchain-ai/langchain) and
  [LiteLLM](https://github.com/BerriAI/litellm) for model/provider boundaries
- [Pydantic](https://docs.pydantic.dev/) for structured contracts
- [FastAPI](https://fastapi.tiangolo.com/) for the runtime API
- [MCP](https://modelcontextprotocol.io/) for optional external tool adapters
- SQLite for checkpoints, run ledgers, schedules, and local state
- Docker Compose for local self-hosting

## Getting Started

### Prerequisites

- Python 3.11 or 3.12
- Git
- Docker with Compose v2, if you want the self-hosted API + console stack
- Optional: provider credentials, local model endpoint, Claude Code, Codex CLI,
  or MCP servers, depending on the backend you choose

### Installation

Clone the repository and install the development extra:

```bash
git clone https://github.com/simon-aibc/agent-os-langgraph.git
cd agent-os-langgraph

python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the zero-LLM deterministic path:

```bash
agent-os "read_file README.md" --thread-id quickstart --sandbox .
```

Expected shape:

```text
[THREAD] quickstart
[SUPERVISOR] -> tool_dispatcher
[TOOL] read_file({"path": "README.md"})
[RESULT] # Agent OS LangGraph ...
```

### Configure Model Roles

Copy the sample environment and select a router, architect, and executor:

```bash
cp .env.example .env
```

The runtime reads these three roles:

```bash
LLM_ROUTER="ollama/qwen2.5:14b"
LLM_ARCHITECT="anthropic/claude-opus-4-8"
LLM_EXECUTOR="openai/gpt-5.5"
```

You may also use authenticated subscription CLIs:

```bash
LLM_ARCHITECT=cli/claude-code
LLM_EXECUTOR=cli/codex
```

Authenticate those CLIs before starting Agent OS. Backend subprocesses are
noninteractive and cannot complete login flows mid-run.

## Usage

### Deterministic Tools

Exact tool commands take the fast path and do not require a model:

```bash
agent-os "read_file README.md" --thread-id readme-demo --sandbox .
agent-os "bash python -m compileall agent_os" --thread-id compile-demo --sandbox .
```

Tier-1 `write` uses a simple `write <path> :: <content>` contract. Shell
quoting happens before Agent OS sees the task, so multiline content must be
expanded by the shell or read from a source file:

```bash
agent-os "write notes.txt :: $(printf 'line1\nline2')" --sandbox ./sandbox
```

### Architect + Human Gate + Executor

Semantic work escalates to a read-only plan, pauses for approval, and only then
allows executor work:

```bash
agent-os "add type hints to math_util.py and verify it compiles" \
  --thread-id type-hints-demo \
  --sandbox ./sandbox
```

At the plan gate, the CLI accepts `approved`, `y`, or `rejected: <reason>`.
Interrupted processes can resume from SQLite without repeating the original
task:

```bash
agent-os --resume --thread-id type-hints-demo --sandbox ./sandbox
```

### Conversations, Sessions, Briefs, And Schedules

Agent OS also supports longer-lived operation:

```bash
agent-os chat --thread-id daily-driver
agent-os sessions list
agent-os sessions inspect daily-driver
agent-os brief --workspace ./examples/personal-assistant
agent-os schedule list
```

Schedules are local cron/interval jobs for `run` and `brief` work. Automatic
firing happens in a long-running `agent-os serve` process or the self-hosted
Compose stack.

### Runtime API

Install the serve extra and start the local API:

```bash
python -m pip install -e ".[serve]"
agent-os serve --host 127.0.0.1 --port 4680
```

Useful endpoints include:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Runtime health |
| `POST /api/runs` | Start a graph run |
| `GET /api/runs` | List runs |
| `GET /api/runs/{id}` | Inspect a run and pending interrupt |
| `GET /api/runs/{id}/events` | Replay and live-tail run events over SSE |
| `POST /api/runs/{id}/approve` | Resume an interrupted run |
| `POST /api/runs/{id}/cancel` | Cancel a nonterminal run |
| `GET /api/graph` | Return memory graph nodes/edges when a memory connector is configured |

The API is localhost-first and is not designed to be exposed directly to the
internet.

## Self-Hosting

Run the backend API and operator console locally with Docker Compose:

```bash
cp .env.example .env
# Edit .env with model roles, provider keys, and AGENT_OS_WORKSPACE.
docker compose up --build --detach
docker compose ps
```

Open the console at [http://127.0.0.1:4100](http://127.0.0.1:4100). The
backend health endpoint is
[http://127.0.0.1:4680/api/health](http://127.0.0.1:4680/api/health).

The Compose stack:

- builds the local backend image;
- mounts `AGENT_OS_WORKSPACE` at `/workspace`;
- stores checkpoints, run ledger, and schedules in the `agentos_data` volume;
- pulls the operator console from an immutable, multi-arch GHCR digest;
- binds both published ports to `127.0.0.1`.

See [docs/self-hosting.md](docs/self-hosting.md) for configuration, backups,
logs, port changes, and security guidance.

## Extending Agent OS

The stable v2 extension surface is `agent_os.api`. Imports from lower-level
`agent_os.*` modules are implementation details and may change in minor
releases.

You can extend Agent OS with:

- `MemoryConnector` implementations for private knowledge bases;
- `BackendAdapter` implementations for model or agent backends;
- `PolicyEngine` implementations for deployment-specific approval rules;
- `RegisteredSkill` objects and trusted local skill packages;
- MCP-backed tool catalogs injected into graph construction.

Minimal native skill example:

```python
from langchain_core.tools import tool

from agent_os.api import RegisteredSkill
from agent_os.default_registry import build_default_registry
from agent_os.graph import build_graph
from agent_os.nodes.tool_dispatcher import build_tool_dispatcher_node


@tool
def summarize(text: str) -> str:
    """Return a compact summary."""
    return text[:200]


registry = build_default_registry()
registry.register(RegisteredSkill("summarize", (), summarize))
dispatcher = build_tool_dispatcher_node(registry=registry)
custom_graph = build_graph(tool_dispatcher_node_impl=dispatcher)
```

See [docs/EXTENDING.md](docs/EXTENDING.md) for connector, backend, policy, and
skill-package contracts.

## Security And Trust Boundaries

Agent OS provides application-level boundaries, not complete isolation.

- Human approval protects agent-planned executor work.
- Explicit Tier-1 `write_file` and `bash` requests are direct user
  instructions.
- Native writes and subprocesses resolve under `AGENT_OS_SANDBOX`.
- Subprocesses use argument arrays, `shell=False`, timeouts, redaction, and
  output caps.
- Checkpoints may contain tasks, messages, plans, tool results, and file
  content; treat them as sensitive local data.
- CLI argument guards and permission modes are defense-in-depth, not an OS
  sandbox.
- Untrusted workloads require a container, microVM, or another isolation layer.

Never commit `.env`, checkpoints, sandboxes, provider credentials, private
vault content, or real workflow logs.

## Roadmap

The first public backbone arc is complete through v2.0.0:

- v1.0-v1.2: typed graph, durable checkpoints, router, MCP, backend profiles
- v1.3-v1.5: generic contracts, memory connectors, chat, sessions, recall
- v1.6-v1.8: policy, workspaces, runtime API, ledger, graph API, scheduler,
  backend container
- v1.9 console: public multi-arch operator console image
- v2.0: stable extension API and one-command self-host Compose

Current v2.x work is focused on community adoption and private deployment
integration rather than expanding the public core by default. See
[docs/roadmap.md](docs/roadmap.md) for the live roadmap and public/private
boundary.

## Contributing

Small, focused issues and pull requests are welcome.

```bash
python -m ruff check .
python -m pytest -W error
python -m pip check
git diff --check
```

The default suite must remain offline. External provider, MCP, Docker, or live
CLI checks should be opt-in and documented. Do not include private memory,
credentials, checkpoints, or real user logs in fixtures.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.

## Contact

Simon Tran - [GitHub @simon-aibc](https://github.com/simon-aibc)

Project link:
[https://github.com/simon-aibc/agent-os-langgraph](https://github.com/simon-aibc/agent-os-langgraph)

## Acknowledgments

- The README structure follows the community-friendly shape popularized by
  [Best-README-Template](https://github.com/othneildrew/Best-README-Template).
- LangGraph, LangChain, LiteLLM, FastAPI, MCP, Docker, Claude Code, and Codex
  provide the ecosystem pieces this reference implementation integrates.
