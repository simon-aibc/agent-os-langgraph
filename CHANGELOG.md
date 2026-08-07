# Changelog

All notable changes are recorded here. The project follows semantic versioning
for public releases.

## [1.5.0] — 2026-08-07

### Added

- Multi-turn conversational loop in CLI via `agent-os chat` command with clean handling of `/exit`, EOF, and Ctrl+C.
- State schema support for multi-turn via `conversation_summary` string in `SimonState` and a generalized summarizer `agent_os/summarize.py` to condense old messages while retaining gist.
- Seamless summarization integration via the active `architect` backend (defaults to `cli/claude-code` when applicable) configured through a new `summary` profile block (`threshold_tokens` and `keep_recent_n`).
- Standardized, conflict-free prompt assembly `[system_task] + [hot_context] + [conversation_summary]` at the `architect` node boundary.
- Session indexing using local SQLite (`agent_os/sessions.py`) providing `agent-os sessions list|inspect|delete` commands and auto-titling for conversation resumption.
- Automated, auto-approved session log appending into the connected vault's `AI/Logs/` path retaining `agent-os` provenance metadata upon chat exit.
- `recall_session` skill providing "hôm qua nói gì về X" capability by bounding `MemoryConnector.search()` scope tightly to the generated `AI/Logs/` path.

## [1.4.0] — 2026-08-07

### Added

- Write-path for memory: `WritableMemory` Protocol (kept separate from read-only `MemoryConnector` so community read-only connectors are not forced to implement it) plus `MemoryWriteResult`.
- `MarkdownVaultConnector.write_note` with `create`/`append`/`overwrite` modes, path-traversal sandbox guard bound to the connector's own `root_path`, and YAML frontmatter round-trip.
- `GbrainConnector.write_note` mapping to gbrain `put_page`, with provenance frontmatter (`agent`/`created`/`via`/`source`) and `agentos/` slug isolation for agent-written notes.
- Approval gate for vault mutation: `MemoryWriteProposal` (added to the checkpoint allowlist) with `evaluate_write_policy` (auto-approve for `AI/Logs/` appends, gate everything else) and `gated_write` reusing the existing `interrupt()` human gate; rejection commits nothing.
- Bounded hot-context injection at the architect boundary via `load_hot_context` (`hot.md` + `AI/Memory/*.md`, `max_chars`/`max_age_days` bounds, no full-vault scan), configured through a profile `HotContextConfig`; `hot_context` state field carries static session-start context, kept distinct from the v1.5 rolling summary.

### Fixed

- Standardized `MemoryConnector` return schema (`ref`-keyed) across `MarkdownVaultConnector` and `GbrainConnector` so interface-bound skills behave identically on both.
- `GbrainConnector` now calls the real gbrain tools (`get_page`, `list_pages`, `query`) instead of non-existent `read_note`/`list_notes`; read-path verified against a live gbrain server rather than mocks.
- `GbrainConnector.read_note` reads frontmatter from gbrain's top-level `frontmatter`/`title` fields (compiled_truth is body-only), so provenance survives a write→read round-trip — a defect the mocks hid, caught by a real integration run on `main`.

### Validation

- 380 offline tests pass with warnings treated as errors (`python -m pytest -W error`); ruff clean.
- Real gbrain read and write→read round-trips verified against a live server (env-gated integration tests), including provenance frontmatter and ephemeral-slug cleanup.

## [1.3.0] — 2026-08-07

### Added

- Core generalization: generic `PlanArtifact`/`ExecutionResult` and `ActionProposal`; `CodingPlan`/`CodingResult` subclasses preserve the coding contract; `ArchitectBrief`/`ExecutorReport` retained as silent aliases (deprecation deferred).
- Connector framework: `Connector` and `MemoryConnector` Protocols with `ConnectorRegistry`; `FilesystemConnector`, `MarkdownVaultConnector` (portable, zero-dependency), and `GbrainConnector` (wrapping the gbrain MCP).
- Skill packages: `manifest.toml` loader with the `vault_qa` example binding the `MemoryConnector` interface, plus a "build your first non-coding skill" tutorial.

### Validation

- 356 offline tests pass with warnings treated as errors; ruff clean.
- Non-coding end-to-end verified through `vault_qa` over `MarkdownVaultConnector` (unmocked).

## [1.2.0] — 2026-08-05

### Added

- `BackendAdapter` Protocol and `BackendRegistry` with collision detection and role validation.
- Migrate `ClaudeCodeAdapter` and `CodexAdapter` off hardcoded factory branches onto the registry.
- Real authentication status checks for the Claude Code and Codex CLI adapters via dedicated read-only subprocess probes.
- `agent-os doctor` subcommand with human-readable table and JSON output covering registered adapters, resolved configuration, checkpoint reachability, warnings, and a health verdict.
- TOML profile loader at `$XDG_CONFIG_HOME/agent-os/profiles.toml` with single-parent one-level `extends` inheritance, secret-key refusal, and precedence resolution `--profile > AGENT_OS_PROFILE > file default > env`.
- `ROUTER_MODE=direct-escalation` to skip Tier-2 structured routing entirely for architect-first workflows; default remains `cascade`.
- Checkpoint `BackendBinding` persistence with resume-time effective-value conflict detection, legacy-checkpoint handling, and `--force-rebind` escape hatch that always warns.
- Antigravity CLI adapter registered as a not-yet-supported stub gated on documented noninteractive invocation and enforceable permission modes; surfaces in `agent-os doctor` under a candidate grouping.

### Validation

- 343 offline tests pass with warnings treated as errors.
- Comprehensive smoke used the Claude Code CLI adapter for both architect and executor roles; Codex adapter coverage is verified by the offline test suite through the shared registry code path.

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

[1.2.0]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.2.0
[1.1.2]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.1.2
[1.1.1]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.1.1
[1.1.0]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.1.0
[1.0.1]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.0.1
[1.0.0]: https://github.com/simon-aibc/agent-os-langgraph/releases/tag/v1.0.0
