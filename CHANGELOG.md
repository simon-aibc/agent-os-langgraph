# Changelog

All notable changes are recorded here. The project follows semantic versioning
for public releases.

## [1.1.2] — 2026-08-03

### Fixed

- Generate OpenAI strict-compatible Codex schemas recursively, including
  `additionalProperties: false` and complete `required` arrays.
- Classify common Claude and Codex authentication failures with actionable
  re-authentication guidance and redacted excerpts.
- Raise structured router acceptance from `0.70` to `0.80` and add semantic
  coding examples that escalate instead of invoking incomplete write tools.

### Validation

- 263 offline tests pass with warnings treated as errors.
- A real Codex executor smoke test edited and compiled a sandbox file and
  returned `ExecutorReport.success=True`.

## [1.1.1] — 2026-08-03

### Fixed

- Close child-process stdin with `DEVNULL` so noninteractive Claude Code calls
  do not wait for piped input.
- Isolate default-suite model configuration from a developer's local `.env`.

## [1.1.0] — 2026-08-03

### Added

- Subscription-backed Claude Code and Codex CLI delegators for architect and
  executor roles.
- Read-only architect permission modes and sandbox-scoped executor modes.
- Shared CLI runner with credential stripping, argument blocking, output
  parsing, timeout handling, and temporary-schema cleanup.

### Design

- Delegate to CLI agents as subprocesses instead of wrapping them as
  `BaseChatModel` instances.
- Retry the read-only architect on transient failures; never automatically
  retry a side-effectful CLI executor.

## [1.0.1] — 2026-08-02

### Fixed

- Resume checkpoints paused mid-run without requiring a pending HITL interrupt.
- Propagate nonzero Bash results to workflow and CLI exit status.
- Document multiline Tier-1 write command escaping.
- Retry transient API-model failures with bounded exponential backoff.

## [1.0.0] — 2026-08-02

### Added

- Typed state and compiled LangGraph workflow.
- Conditional supervisor, three-tier dispatcher, architect, human gate, and
  sandboxed executor.
- SQLite persistence with restart/resume coverage.
- Native tools, optional MCP loading, streaming CLI, and security boundaries.
- Prompt caching, message trimming, and retained-output caps.
- Python 3.11/3.12 CI, Ruff, warnings-as-errors tests, and MIT license.

[1.1.2]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.1.2
[1.1.1]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.1.1
[1.1.0]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.1.0
[1.0.1]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.0.1
[1.0.0]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.0.0
