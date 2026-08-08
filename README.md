# Agent OS LangGraph

[![CI](https://github.com/simon-aibc/agent-os-langgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/simon-aibc/agent-os-langgraph/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.11–3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)
![Tests: 408 passing](https://img.shields.io/badge/tests-408%20passing-brightgreen.svg)
[![Release](https://img.shields.io/github/v/release/simon-aibc/agent-os-langgraph)](https://github.com/simon-aibc/agent-os-langgraph/releases/latest)
![Dependencies pinned](https://img.shields.io/badge/dependencies-pinned-informational.svg)

An open-source backbone for building durable, controllable AI agent systems.
Deterministic tools handle known work; ambiguous work escalates through an architect, human plan gate, and sandboxed executor.
Typed state, durable SQLite checkpoints, MCP adapters, and an offline-tested streaming CLI demonstrate production engineering.

**Current release:** [v1.5.0](https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.5.0) ·
[Changelog](CHANGELOG.md) · [Product specification](docs/PRD.md) ·
[Architecture](docs/architecture.md) · [Roadmap](docs/roadmap.md)

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

## 30-second quickstart

```bash
git clone https://github.com/simon-aibc/agent-os-langgraph.git
cd agent-os-langgraph

python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

# Deterministic Tier-1 path: no LLM or network required.
agent-os "read_file README.md" --thread-id quickstart --sandbox .
```

Expected structure:

```text
[THREAD] quickstart
[SUPERVISOR] → tool_dispatcher
[TOOL] read_file({"path": "README.md"})
[RESULT] # Agent OS LangGraph ...
```

### End-to-end coding workflow

A semantic task misses the deterministic tool path, produces a read-only plan,
pauses for approval, and only then allows the executor to edit and verify:

```text
$ agent-os "add type hints to math_util.py and verify it compiles" \
    --thread-id type-hints-demo --sandbox ./sandbox

[THREAD] type-hints-demo
[SUPERVISOR] → tool_dispatcher
[SUPERVISOR] → architect
[HUMAN] Review the proposed implementation plan.
> approved
[SUPERVISOR] → executor
[SUPERVISOR] → __end__
```

The checkpoint remains resumable if the process is interrupted before the
final node. Provider subprocesses do not expose private reasoning; the CLI
shows graph transitions, tool boundaries, and validated result contracts.

For architect/executor workflows, copy [.env.example](.env.example) to `.env`,
configure `LLM_ROUTER`, `LLM_ARCHITECT`, and `LLM_EXECUTOR`, then run:

```bash
agent-os "refactor the target module and add regression tests" \
  --thread-id refactor-demo \
  --sandbox ./sandbox
```

At the plan gate the CLI pauses inline and accepts `approved`, `y`, or
`rejected: <reason>`. A stopped process resumes from SQLite without repeating
the original task. If the process stops mid-run outside a human gate, `--resume`
continues from the next checkpointed node:

```bash
agent-os --resume --thread-id refactor-demo --sandbox ./sandbox
# Equivalent entrypoint: python -m agent_os ...
```

## Tier-1 Command Escaping

Tier-1 `write` is intentionally simple: `write <path> :: <content>`. Shell
quoting still happens before Agent OS sees the task, so multiline content needs
command substitution or a source file.

```bash
# WRONG: writes literal backslash-n characters.
agent-os "write foo.txt :: line1\nline2"

# RIGHT: let the shell expand real newlines before Agent OS receives the task.
agent-os "write foo.txt :: $(printf 'line1\nline2')"

# RIGHT: write content from an existing template file.
agent-os "write foo.txt :: $(cat template.txt)"
```

## Beyond one-shot runs

Agent OS supports continuous, multi-turn, and background operations beyond basic one-shot execution:

- `agent-os chat` provides multi-turn conversations and seamless workflow resumption.
- `agent-os sessions list|inspect|delete` manages durable session state.
- `agent-os brief` runs autonomous briefing engines.
- `agent-os serve` provides a localhost FastAPI interface (`[serve]` extra) to integrate with external dashboards.

## Architecture

- `SimonState` is a `TypedDict`; complex boundaries such as `ArchitectBrief`,
  `RouterDecision`, and `ExecutorReport` are Pydantic models.
- The supervisor uses explicit routing precedence. The dispatcher can terminate
  directly on tool success or return to the supervisor for agent escalation.
- The architect has read-only planning tools. Its brief reaches `human_gate`
  before the executor agent can edit files or run verification commands.
- LangGraph `interrupt()` plus a SQLite checkpointer preserves pending work by
  `thread_id`, including across process restarts.
- The CLI consumes `astream_events(version="v2")` and prints model tokens,
  node routes, tool calls, and results—never private chain-of-thought.

See [docs/architecture.md](docs/architecture.md) for routing precedence,
state rationale, trust boundaries, and the decision log. The approved product
requirements are in [docs/PRD.md](docs/PRD.md).

## What each milestone demonstrates

| Milestone | Implemented capability | Why it matters |
|---|---|---|
| R1 | Typed state and compiled graph skeleton | Understands LangGraph state and graph construction |
| R2 | Conditional supervisor routing and bounded recursion | Designs deterministic control flow instead of prompt-only routing |
| R3 | Read-only architect subgraph with structured brief | Separates planning from execution and tests agents offline |
| R4 | Executor subgraph with path checks, `shell=False`, and timeouts | Treats tool execution as a security boundary |
| R5 | Interrupt-driven human plan gate | Adds approval before agent-planned side effects |
| R6 | SQLite checkpoints and restart/resume tests | Builds workflows that survive process failure |
| R7 | Three-tier router, pluggable registry, and MCP adapters | Balances deterministic speed, model judgment, and extensibility |
| R8 | Rich streaming CLI with durable resume | Delivers an operator-facing interface with explicit failure semantics |
| R9 | Public documentation, CI, lint, and repo hardening | Treats maintainability and presentation as product requirements |
| R11 | Prompt caching, trimming, retries, and output caps | Makes model cost and retained data explicit boundaries |
| v1.0.1 | Resume, Bash status, write docs, and retry fixes | Converts dogfood findings into regression-tested patches |
| v1.1.x | Claude Code and Codex CLI delegators | Integrates subscription agents without pretending they are raw chat models |
| v1.2.x | Backend portability and profiles | Resolves tight coupling via an explicit BackendAdapter Protocol |
| v1.3.x | Generic contracts, connector framework, and skill packages | Escapes the coding-agent shape into a domain-agnostic backbone |
| v1.4.x | Memory write-path with an approval gate, provenance, and bounded hot-context | Treats agent memory writes as authority-gated actions |
| v1.5.x | Conversational chat loop, session management, summarize-before-trim, and cross-session recall | Turns durable state into a multi-turn operator experience |

## Extending Agent OS

### Register a native tool

`RegisteredSkill` accepts LangChain `BaseTool` objects or plain callables. A
custom skill becomes available to the structured router without changing the
dispatcher:

```python
from langchain_core.tools import tool

from agent_os.default_registry import build_default_registry
from agent_os.graph import build_graph
from agent_os.nodes.tool_dispatcher import build_tool_dispatcher_node
from agent_os.skills import RegisteredSkill


@tool
def summarize(text: str) -> str:
    """Return a compact summary."""
    return text[:200]


registry = build_default_registry()
registry.register(RegisteredSkill("summarize", (), summarize))
dispatcher = build_tool_dispatcher_node(registry=registry)
custom_graph = build_graph(tool_dispatcher_node_impl=dispatcher)
```

### Load MCP tools

```python
from agent_os.default_registry import build_default_registry_with_mcp
from agent_os.graph import build_graph
from agent_os.nodes.tool_dispatcher import build_tool_dispatcher_node


async def build_mcp_graph():
    registry = await build_default_registry_with_mcp()
    dispatcher = build_tool_dispatcher_node(registry=registry)
    return build_graph(tool_dispatcher_node_impl=dispatcher)
```

Enable servers with `MCP_FILESYSTEM_ENABLED`, `MCP_CODEGRAPH_ENABLED`, and
`MCP_GBRAIN_URL`. `MCP_CODEGRAPH_COMMAND` overrides the CodeGraph executable.

> `from agent_os.graph import graph` intentionally uses native tools only.
> Environment flags do not auto-load MCP tools into that default graph; use the
> asynchronous registry construction and dispatcher injection shown above.

### Swap LLMs

Model roles use provider/model strings from `.env`. Tests or applications may
also inject any compatible `BaseChatModel` into `build_architect_agent()`,
`build_executor_agent()`, or `build_tool_dispatcher_node()`.

## Using subscription CLI tools

Agent OS can delegate work to installed subscription tools instead of making
direct per-token API calls. This avoids separate API billing by using an
existing subscription, subject to the provider's plan and rate limits.

| Available access | Architect | Executor | Supported |
|---|---|---|:---:|
| Claude Code only | `cli/claude-code` | `cli/claude-code` | Yes |
| Codex only | `cli/codex` | `cli/codex` | Yes |
| Claude Code + Codex | `cli/claude-code` | `cli/codex` | Yes |
| API-backed models | LiteLLM-compatible model | LiteLLM-compatible model | Yes |
| Antigravity (candidate) | — | — | Not yet |
| Hermes CLI | — | — | Not yet; requires a delegator adapter |

The Antigravity adapter registers as a not-yet-supported stub; see
[docs/v1.2-portability.md](docs/v1.2-portability.md) for its acceptance
criteria.

The router is configured independently. It can use a local Ollama model or any
LiteLLM-compatible structured-output model; it does not require the same
provider as the architect or executor.

```bash
# Check authentication before invoking agent-os.
claude auth status
codex login status

# Authenticate first when either status check fails.
claude auth login
codex login

export LLM_ARCHITECT=cli/claude-code
export LLM_EXECUTOR=cli/codex

agent-os "refactor the target module" --thread-id cli-demo
```

> **Authentication note:** Backend subprocesses receive `stdin=DEVNULL`, so
> they cannot complete an interactive login or re-authentication during a
> workflow. Automatic token refresh may still work when the CLI supports it;
> otherwise authenticate outside Agent OS before starting the workflow.

The delegators apply fixed permission modes and reject known access-expansion
arguments:

- **Architect modes:** Claude uses `plan` mode; Codex uses `read-only` mode.
- **Executor modes:** Claude uses `acceptEdits`; Codex uses `workspace-write`.
- The shared runner rejects cwd overrides, `--add-dir`, and dangerous bypass
  flags.

The read-only CLI Architect may retry transient network or rate-limit failures.
The side-effectful CLI Executor never auto-retries because partial edits may
already exist in the sandbox; its error tells the operator to inspect the
working tree before resuming.

Compared with direct API calls, subscription CLIs have process startup overhead
and do not expose their internal reasoning stream to Agent OS. The current graph
also invokes roles sequentially. A typical architect/executor turn takes roughly
15–30 seconds, but latency varies by task, provider, and subscription limits.

> **Security note:** CLI argument guards, a fixed `cwd`, and permission modes
> are defense-in-depth—not OS or container isolation. They do not guarantee
> untrusted code cannot touch external paths. Use a container or microVM for
> untrusted workloads.

### CLI backend troubleshooting

- **Authentication failure:** run `claude auth login` or `codex login` outside
  Agent OS, then repeat the task or resume its checkpoint.
- **Partial executor failure:** inspect the sandbox before resuming. Agent OS
  never automatically retries a side-effectful CLI executor.
- **Completed thread cannot resume:** use a new `--thread-id`; completed graphs
  have no pending node.
- **Provider binary missing:** confirm `claude` or `codex` is on `PATH` in the
  same shell that launches `agent-os`.

## Token Economy

Every LLM call is a cost boundary. Deterministic tools form the free, fast
path; model-backed routing and agent steps are bounded explicitly.

| Pattern | Description |
| :--- | :--- |
| Structured outputs | Pydantic contracts bound the shape of model responses. |
| Cascading router | Tier 1 is deterministic; Tier 2 uses a cheaper model before Tier 3 agent escalation. |
| HITL gate | Executor work starts only after the proposed plan is approved. |
| Anthropic prompt caching | Ephemeral `cache_control` blocks target up to 90% lower cost for eligible cached-input tokens. |
| 8K message trimming | Architect and Executor invocation histories are trimmed before model calls. |
| Output caps | Bash streams are capped at 100KB each; serialized dispatcher results at 50KB total. |
| Offline startup | CLI initialization uses LiteLLM's local cost map and avoids incidental provider calls. |
| Transient retries | API Architect/Executor calls and the read-only CLI Architect retry 429, 503, and timeout errors with 2/4/8s backoff; the CLI Executor does not. |

### Illustrative benchmark

These estimates depend on the model, provider, and workload; they are not
measured SLAs.

- **Tier 1 (Deterministic)** = $0 / ~0ms LLM latency
- **Tier 2 (Structured LLM)** = ~$0.0002 / ~200ms
- **Tier 3 (Agent Escalation)** = ~$0.01 / ~2s
- **Subscription CLI (Claude/Codex)** = $0 marginal cost / ~15–30s per
  architect/executor turn (approximate; varies by task and provider limits)

### Output limits

Bash standard output and error are truncated independently to 100KB (UTF-8
bytes) each. Total serialized dispatcher tool results are capped at 50KB.
Subprocess capture still buffers in memory before truncation; containerized,
streamed execution remains v2.

## Security and trust boundaries

- The HITL gate protects **agent-planned executor work**. Explicit Tier-1
  commands such as `write_file ...` or `bash ...` are treated as direct user
  instructions and execute without an additional approval prompt.
- Native writes and subprocesses use `AGENT_OS_SANDBOX` (default `./sandbox`).
  CLI `--sandbox` also constrains reads for that invocation. These are path/cwd
  controls, not OS or container isolation.
- Subprocesses use argument arrays, `shell=False`, captured output, and a
  timeout. Untrusted models or commands still require a container.
- The filesystem MCP server additionally requires its resolved root to be
  strictly below the user home. Every enabled MCP server extends the trust
  boundary and must be trusted.
- SQLite checkpoints may contain tasks, messages, plans, tool results, and
  file content. They are gitignored and should be protected as sensitive data.
- Checkpoint deserialization allowlists application Pydantic types. CLI tool
  arguments redact common credential fields before display.
- CLI startup uses LiteLLM's local model-cost map, avoiding an incidental
  metadata request before the workflow begins.
- Bash and dispatcher results are byte-capped before checkpoint storage. The
  subprocess capture itself remains an in-memory boundary, not an OS resource
  limit.

## CLI exit codes

| Code | Meaning |
|---:|---|
| `0` | Workflow completed successfully |
| `1` | Workflow, graph execution, or Tier-1 tool execution failed |
| `2` | Invalid CLI/configuration/resume request |
| `130` | Interrupted with Ctrl+C; checkpoint preserved when available |

## Development and testing

```bash
python -m ruff check .
python -m pytest -W error
```

The default suite is offline and deselects real MCP integration tests. Run an
enabled integration explicitly, for example:

```bash
MCP_FILESYSTEM_ENABLED=true \
AGENT_OS_SANDBOX="$HOME/agent-os-sandbox" \
python -m pytest -m integration tests/test_mcp_integration.py
```

CI runs Ruff and the offline test suite on Python 3.11 and 3.12.

See [CHANGELOG.md](CHANGELOG.md) for release history. External integration
tests remain opt-in so a fresh clone never requires paid provider access.

## Roadmap

See [docs/roadmap.md](docs/roadmap.md) for current state, north star goals, and the public milestone sequence.

Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities
privately according to [SECURITY.md](SECURITY.md).

Licensed under the [MIT License](LICENSE).
