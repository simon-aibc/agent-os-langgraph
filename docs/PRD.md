# Agent OS LangGraph — public product specification

- **Current version:** 1.5.0
- **Status:** Released
- **License:** MIT
- **Runtime:** Python 3.11+
- **Repository:** https://github.com/simon-aibc/agent-os-langgraph
- **Quality gate:** 263 offline tests, `pytest -W error`, Ruff, Python 3.11/3.12 CI

## 1. Product summary

Agent OS LangGraph is a local-first coding-agent orchestrator built with
LangGraph. It sends exact, low-risk commands through deterministic tools and
escalates ambiguous coding work through a read-only architect, a human plan
gate, and a sandbox-scoped executor.

The project demonstrates production-oriented agent patterns without claiming
to provide operating-system isolation:

- explicit typed state and routing precedence;
- structured contracts between agent roles;
- human approval before agent-planned writes;
- durable SQLite checkpoints and cross-process resume;
- bounded subprocess execution and output retention;
- native, MCP, API-model, and subscription-CLI extension points.

## 2. Target users

### Agent engineers

Developers who need a reference implementation for stateful LangGraph
workflows, supervisor routing, human-in-the-loop interrupts, and durable local
execution.

### Local automation builders

Users who want to run coding workflows with API-backed models, local models,
or already-authenticated Claude Code and Codex subscriptions.

### Technical reviewers

Hiring managers and client engineering teams evaluating concrete examples of
agent boundaries, failure handling, tests, and security trade-offs.

## 3. User journey

For a semantic coding request such as “add type hints and verify compilation”:

1. `planner` preserves the task and initializes graph state.
2. `supervisor` sends the unresolved task to `tool_dispatcher`.
3. The dispatcher attempts deterministic parsing, then structured routing.
4. A semantic coding task escalates to the read-only `architect`.
5. `architect` returns an `ArchitectBrief` containing files, changes, and a
   verification command.
6. `human_gate` pauses execution until the user approves or rejects the plan.
7. On approval, `executor` applies the plan and returns an `ExecutorReport`.
8. Successful execution terminates; rejected plans return to the architect.
9. SQLite checkpoints preserve resumable state throughout the workflow.

## 4. Functional requirements

### State and graph

- The graph uses a typed `SimonState` with Pydantic boundary artifacts.
- Node destinations are explicit and testable.
- Routing loops are bounded by a configurable recursion limit.

### Cascading dispatcher

- Tier 1 parses exact native commands without an LLM.
- Tier 2 uses a structured-output router against the registered tool catalog.
- Decisions below the `0.80` confidence threshold escalate safely.
- Tool exceptions and missing required arguments return structured failures.

### Architect

- The native architect agent has read-only tools.
- CLI architects run in Claude `plan` or Codex `read-only` mode.
- Every architect returns a validated `ArchitectBrief`.
- Read-only transient failures may be retried.

### Human gate

- Every agent-generated implementation plan pauses before executor work.
- Accepted values normalize to `approved` or `rejected: <reason>`.
- Invalid CLI feedback is re-prompted without advancing graph state.

### Executor

- Native write and process tools resolve under `AGENT_OS_SANDBOX`.
- Subprocesses use argument arrays, `shell=False`, timeouts, and captured output.
- CLI executors run in Claude `acceptEdits` or Codex `workspace-write` mode.
- CLI executors are not automatically retried because partial edits may exist.
- Every executor returns a validated `ExecutorReport`.

### Persistence and CLI

- SQLite checkpoints survive process restarts by `thread_id`.
- The CLI supports new tasks, HITL resume, and mid-run resume.
- Observable graph, model, and tool events stream without exposing hidden
  chain-of-thought.
- Exit codes distinguish success, failure, invalid usage, and interruption.

### Extensibility

- `SkillRegistry` accepts native callables and LangChain tools.
- MCP servers load independently so one unavailable server does not remove
  healthy tools.
- Architect, executor, router, dispatcher, and checkpointer implementations
  can be injected for tests or deployment-specific behavior.

## 5. Security requirements and limits

- Secrets and credential-like environment variables are removed from child
  process environments where practical and redacted from error excerpts.
- CLI arguments that expand filesystem access or bypass permission controls
  are rejected.
- Codex output schemas recursively require known properties and reject
  additional properties.
- Bash output is retained at no more than 100 KiB per stream; dispatcher output
  is retained at no more than 50 KiB.
- Checkpoint deserialization allowlists application model types.
- Checkpoints, sandboxes, credentials, and local dogfood logs remain ignored by
  Git.

These are application-level controls. They do not isolate the network, child
processes, CPU, memory, or the host filesystem from hostile executable code.
Untrusted workloads require a container or microVM.

## 6. Supported backends

| Role | Supported paths |
|---|---|
| Router | Any LiteLLM-compatible structured-output model, including local Ollama |
| Architect | LiteLLM-compatible model, `cli/claude-code`, or `cli/codex` |
| Executor | LiteLLM-compatible model, `cli/claude-code`, or `cli/codex` |
| Tools | Native registry and optional MCP adapters |
| Checkpoint | SQLite by default; in-memory injection for tests |

Claude-only, Codex-only, and mixed Claude/Codex role configurations are valid.
Other agent CLIs require a new delegator that implements the same structured
contracts; they are not automatically supported by accepting a model name.

## 7. Non-goals for v1.5

- OS-level isolation for untrusted code.
- Hosted multi-user service or distributed checkpoint database.
- Automatic loading of every local MCP server or personal skill.
- Vault memory, personal-profile injection, Telegram, cron, dashboard, or TUI.
- Adapters for Hermes, Antigravity, or arbitrary third-party agent CLIs.
- Display of private model reasoning or chain-of-thought.

## 8. Release acceptance

A release is accepted when:

- the offline suite passes with warnings treated as errors;
- Ruff and dependency checks pass;
- CI succeeds on Python 3.11 and 3.12;
- no secrets or runtime state are tracked;
- user-facing behavior and security limitations are documented;
- provider-specific changes have a contract test that does not require paid
  network access in the default suite.

Release history is maintained in [`CHANGELOG.md`](../CHANGELOG.md). Detailed
control-flow rationale lives in [`architecture.md`](architecture.md), and
future work lives in [`roadmap.md`](roadmap.md).
