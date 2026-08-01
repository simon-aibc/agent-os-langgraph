# Agent OS architecture

This document describes the graph implemented in the repository today. Product
intent and future requirements live in the [approved PRD](PRD.md).

## System overview

Agent OS separates orchestration into a deterministic graph and bounded agent
roles:

- `planner` preserves a structured brief or initializes the plan from the task.
- `supervisor` converts state into an explicit graph destination.
- `tool_dispatcher` handles known tools or escalates ambiguous work.
- `architect` creates a structured plan using read-only tools.
- `human_gate` pauses that plan for approval or rejection.
- `executor` edits and verifies within the configured native sandbox.

The graph is assembled in [`agent_os/graph.py`](../agent_os/graph.py).

```mermaid
flowchart TD
    START(["START"]) --> planner["planner"] --> supervisor["supervisor"]
    supervisor -->|"new task"| dispatcher["tool_dispatcher"]
    dispatcher -->|"tool success"| END(["END"])
    dispatcher -->|"low confidence or failure"| supervisor
    supervisor -->|"escalated"| architect["architect"]
    architect --> gate["human_gate"]
    gate -->|"resume"| supervisor
    supervisor -->|"approved"| executor["executor"]
    supervisor -->|"rejected"| architect
    executor --> supervisor
    supervisor -->|"execution complete"| END
```

The dispatcher returns `Command(goto=END)` on success, so that path does not
pass through the supervisor again. Architect, gate, and executor edges are
explicit; supervisor destinations are conditional.

## State and boundary models

[`SimonState`](../agent_os/state.py) is a `TypedDict`, which lets LangGraph own
state-channel behavior without wrapping the entire graph state in a runtime
model. `messages` uses LangGraph's `add_messages` reducer. Complex values cross
node boundaries as Pydantic models from
[`agent_os/schemas.py`](../agent_os/schemas.py).

| Field | Type | Purpose |
|---|---|---|
| `messages` | `list[AnyMessage]` with reducer | Conversation and model messages |
| `task` | `str` | Original user instruction |
| `plan` | `str \| ArchitectBrief \| None` | Initial plan text or architect contract |
| `executor_output` | `str \| ExecutorReport \| None` | Legacy text or structured execution report |
| `human_feedback` | `str \| None` | `approved` or `rejected: <reason>` |
| `hot_context` | `str \| None` | Reserved compact context channel |
| `tool_result` | optional `ToolExecutionResult \| None` | Serialized dispatcher result |
| `router_escalated` | optional `bool` | Dispatcher-to-supervisor escalation signal |

This hybrid keeps state updates lightweight while validating plans, router
decisions, tool results, and executor reports at their boundaries. The removed
boolean `approval` field is intentionally not migrated; new checkpoints use
the richer `human_feedback` contract.

## Routing precedence

[`route_from_state()`](../agent_os/routing.py) evaluates conditions in this
exact order:

| Priority | Condition | Route | Reason |
|---:|---|---|---|
| 1 | Successful `ExecutorReport` | `end` | Execution completed |
| 2 | `human_feedback == "approved"` | `executor` | Run the reviewed plan |
| 3 | Feedback begins with `rejected:` | `architect` | Revise using the reason |
| 4 | `executor_output` is a legacy string | `end` | Preserve the remaining text-output contract |
| 5 | `plan` is an `ArchitectBrief` with no feedback | `end` | Do not execute an undecided plan |
| 6 | `router_escalated is True` | `architect` | Tool routing could not safely resolve the task |
| 7 | Otherwise | `tool` | Give the lowest-cost dispatcher the first attempt |

The function does not inspect `ToolMessage`, `AIMessage.tool_calls`, or model
prose. [`supervisor_node`](../agent_os/nodes/supervisor.py) maps the logical
route to a concrete node and returns a LangGraph `Command`.

An approved workflow with a failed executor report retries the executor. The
default runtime recursion limit of seven graph steps bounds this retry shape
and other accidental loops.

## Three-tier dispatcher

[`agent_os/nodes/tool_dispatcher.py`](../agent_os/nodes/tool_dispatcher.py)
implements three progressively more expensive paths:

1. **Deterministic:** an exact canonical name or alias in the first task token
   is parsed for the native `read_file`, `write_file`, and `bash` contracts.
2. **Structured model:** unresolved text is classified into a
   `RouterDecision` against the injected registry catalog.
3. **Escalation:** confidence below `0.70`, an unknown tool, parser failure, or
   tool exception returns to the supervisor with `router_escalated=True`.

A successful tool invocation stores `ToolExecutionResult` and goes directly to
`END`. The default registry is native-only. MCP tools are loaded asynchronously
and require an injected registry/dispatcher; environment flags alone do not
modify the module-level default graph.

## Human gate and durable resume

The architect's only outgoing edge is `human_gate`. The node calls LangGraph
`interrupt()` with the serialized `ArchitectBrief`. At that point:

1. the checkpointer persists state under `configurable.thread_id`;
2. the CLI reads the pending interrupt from the state snapshot;
3. invalid input is rejected locally without advancing the graph;
4. `Command(resume="approved")` continues to the supervisor and executor;
5. `Command(resume="rejected: ...")` returns through the architect and pauses
   on a revised brief.

The default graph uses synchronous `SqliteSaver`. The streaming CLI builds the
same graph with `AsyncSqliteSaver`, consumes `astream_events(version="v2")`,
and proves resume with a fresh graph/checkpointer context. The checkpoint
serializer allowlists application Pydantic types instead of permitting
arbitrary msgpack reconstruction. See
[`agent_os/checkpoints.py`](../agent_os/checkpoints.py) and
[`agent_os/cli/app.py`](../agent_os/cli/app.py).

## Sandbox and trust boundaries

The repository uses multiple related controls rather than claiming a complete
OS sandbox:

- Native writes, bash commands, and tests operate under `AGENT_OS_SANDBOX`,
  defaulting to `./sandbox`. Bash receives an argument list, uses
  `shell=False`, captures output, and has a timeout.
- CLI `--sandbox` also makes read/grep roots resolve from that directory for
  the duration of the invocation. Without an explicit sandbox, read-only
  architect tools retain their project-cwd behavior.
- The filesystem MCP integration is stricter: its resolved root must be below,
  but not equal to, the current user home. Root, system directories, and
  symlink escapes are rejected.
- Other stdio and HTTP MCP servers are trusted external processes/services.
  Per-server connection failures are isolated, but enabling a server expands
  the trust boundary.

These controls do not isolate executables, networks, CPU, memory, or child
processes. Untrusted workloads require a container or microVM. Explicit Tier-1
write/bash commands are direct user instructions and do not pass through the
architect/HITL plan loop.

## Extension points

- Register `RegisteredSkill` instances in an injected `SkillRegistry`.
- Supply `MCPServerConfigs` or an `MCPClientFactory`, then inject the resulting
  dispatcher into `build_graph()`.
- Inject compatible chat models into architect, executor, or smart-router
  factories.
- Replace architect, executor, dispatcher, or checkpointer implementations in
  `build_graph()` for deterministic tests or deployment-specific behavior.
- Use `InMemorySaver` for isolated tests and SQLite for durable workflows.

## Decision log

| Decision | Rationale | Trade-off |
|---|---|---|
| TypedDict state plus Pydantic artifacts | Fits LangGraph channels while validating complex boundaries | Full state validation is not automatic on every update |
| Conditional supervisor plus `Command` destinations | Makes routing observable and independently testable | Precedence must remain documented and covered by tests |
| Human plan gate before executor | Prevents autonomous agent-planned writes before review | Explicit deterministic write/bash commands remain direct operations |
| SQLite checkpointer | Local, portable, and sufficient for cross-process resume | Not a multi-host production database |
| Native-only default registry | Import and sync graph construction stay predictable | MCP users must build and inject an async-loaded registry |
| Per-server MCP loading | One unavailable server does not remove healthy tools | Startup may contain a partial tool catalog |
| Remove boolean `approval` | Rejection reasons belong in one normalized feedback field | Old checkpoints containing only `approval` are not migrated |
| Async CLI over the same graph | Enables event streaming without duplicating orchestration | Requires an async SQLite saver in the CLI boundary |
| No chain-of-thought display | Streams observable outputs without presenting hidden reasoning | Operators see contracts and events, not private model deliberation |
