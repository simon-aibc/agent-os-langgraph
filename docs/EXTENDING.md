# Extending Agent OS

Agent OS v2 guarantees compatibility only for the names in `agent_os.api`.
Imports from other `agent_os.*` modules are implementation details and may change in a
minor release. Existing public signatures and documented behavior remain compatible
through v2; an incompatible change requires a v3 release, migration notes, and a
reviewed update to the public API contract fixture.

## Memory connectors

A memory connector is synchronous and read-only. Register one under an application
chosen name:

```python
from agent_os.api import ConnectorRegistry


class Notes:
    name = "notes"

    def search(self, query: str, limit: int = 10) -> list[dict]:
        return [{"slug": "welcome", "text": query}][:limit]

    def read_note(self, slug_or_path: str) -> dict:
        return {"slug": slug_or_path, "text": "Hello"}

    def list_notes(self, filters: dict | None = None) -> list[dict]:
        return [{"slug": "welcome"}]


connectors = ConnectorRegistry()
connectors.register("notes", Notes())
notes = connectors.resolve("notes")
```

Errors raised by connector implementations propagate to their caller. Connectors
should return the documented dictionary/list shapes and must not hide writes behind
these read methods.

## Backend adapters

Adapters declare the graph roles they support and return a synchronous invoker.

```python
from agent_os.api import AuthStatus, BackendRegistry, ExecutionResult


class LocalBackend:
    name = "local"
    binary_name = "local-agent"
    supported_roles = frozenset({"executor"})
    stub = False

    def build_invoker(self, role):
        if role not in self.supported_roles:
            raise ValueError(f"unsupported role: {role}")

        def invoke(state):
            return ExecutionResult(status="completed", outputs={"task": state["task"]})

        return invoke

    def authentication_status(self):
        return AuthStatus(status="ok", detail="local")


backends = BackendRegistry()
backends.register(LocalBackend())
adapter = backends.resolve("executor", "local")
```

Authentication details must be safe to display and must never contain credentials.
Unsupported roles and invalid output should fail explicitly rather than silently
falling back to another backend.

## Policies

Policies synchronously decide whether a proposed action is allowed, denied, or needs
approval. `apply_policy` executes only an allowed proposal; approval uses the runtime's
human-interrupt path.

```python
from agent_os.api import PolicyDecision, apply_policy


class ReadOnlyPolicy:
    def evaluate(self, proposal, *, workspace=None, context=None):
        decision = "allow" if proposal.side_effect in {"none", "read"} else "deny"
        return PolicyDecision(decision=decision, policy_id="read-only")


# result = apply_policy(ReadOnlyPolicy(), proposal, execute_fn=execute)
```

### Policy Modes

- **`manual` (default)**: Evaluates safely scoped learned memory rules, active session grants, built-in log/brief rules, and the 7-level taxonomy (`read`/`none` → `allow`, `write`/`network`/`communication` → `require_approval`, `payment`/`privileged` → `deny`). Requires interactive human approval for unknown low/medium actions.
- **`smart`**: Operates as a tested alias of `manual` with identical safety boundaries.
- **`off`**: Explicit **unsafe local-only escape hatch** that bypasses all policy checks and auto-allows all actions (including `payment` and `privileged`). Intended strictly for isolated sandbox testing.

### User-Taught Permission Learning

Agent OS uses explicit, user-taught permission learning rather than autonomous self-learning:
- **Approve once** (`approved`, `y`): Grants access only for the immediate action.
- **Session** (`session`): Grants access to the same safely scoped memory action for the current CLI invocation or server run. It is cleared when that session ends.
- **Always approve** (`always_approve`): Persists an allow rule to SQLite across restarts.
- **Always deny** (`always_deny`): Persists a deny rule to SQLite across restarts.
- **Reject** (`rejected`, `n`): Cancels the action execution.

In this release, remembered rules deliberately apply **only** to `memory.write`.
Each key includes the actual connector, write mode, and full note ref:

```text
memory_write:write:<connector>:<create|append|overwrite>:<ref>
```

For example, approval to create a note never authorizes overwriting that note,
and a `markdown_vault` rule never authorizes a `gbrain` write. Generic file,
network, and communication tools do not yet expose a canonical destination
schema, so `session` and `always_*` are rejected for them; use one-time
`approved` instead. `payment` and `privileged` are denied before any rule is
read (except the explicitly unsafe `mode = "off"` escape hatch).

The shipped native action is `memory_write [create|append|overwrite] <ref> :: <content>`.
`MarkdownVaultConnector` supports all three modes. Gbrain currently exposes
only an upsert (`put_page`), so it accepts only an explicit `overwrite`;
`create` and `append` fail before prompting or saving a learned rule rather
than silently overwriting a page.

For a workspace, rules live in `<workspace>/permissions.db`. Set
`AGENT_OS_PERMISSIONS_DB` to explicitly override that location. The composed
workspace policy is bound into CLI graph streams and server runs, so a nested
`gated_write()` uses the right workspace and session without callers having to
manually thread an engine.

Learned rules can be inspected and revoked via the CLI:
```bash
agent-os permissions list
agent-os permissions list --json
agent-os permissions revoke <permission-key>
agent-os permissions list --workspace path/to/workspace.toml
```
Or via the Runtime API:
- `GET /api/permissions`
- `DELETE /api/permissions/{permission_key}`

The local CLI does not need an admin token. Runtime API management is disabled
until `AGENT_OS_PERMISSIONS_ADMIN_TOKEN` is set; then send that token using
`X-Admin-Token` or `Authorization: Bearer …`. This prevents an exposed server
from becoming an unauthenticated permission-administration surface.

### Structured observation and outcome evidence

Terminal Runtime runs add one structured observation with `outcome_signal =
unknown`. A completed run is **not** evidence of user acceptance. Operators
may explicitly label the observation `accepted`, `rejected`, or `edited`:

```bash
agent-os observations list --workspace path/to/workspace.toml
agent-os observations record-outcome <observation-id> --signal edited \
  --evidence "Adjusted the artifact before use" --workspace path/to/workspace.toml
```

The same data is available through the private execution API:

- `GET /api/observations`
- `POST /api/observations/{observation_id}/outcome`

Stores live in `<workspace>/observations.db` (or standalone
`./observations.db`), unless `AGENT_OS_OBSERVATIONS_DB` explicitly overrides
the path. The records contain bounded operational metadata only; they never
store the task, model output, tool arguments, or memory contents. Recent
same-kind labelled outcomes may be supplied to the architect as clearly marked
advisory evidence. They never grant a permission, execute a tool, or
automatically change behaviour.

Private Runtime API endpoints (runs, sessions, briefs, schedules, graph, and
chat) are local-only by default. A non-loopback caller must configure
`AGENT_OS_EXECUTION_TOKEN` and send it as `X-Execution-Token` or
`Authorization: Bearer …`; `agent-os serve --host 0.0.0.0` refuses to start
without it. Browser-originated requests must also use an exact origin listed in
`AGENT_OS_CORS_ORIGINS`; this includes WebSocket handshakes and prevents a
third-party page from submitting an approval to the local agent. For a browser
WebSocket, offer `agent-os` and `agent-os-token.<base64url-token>` as
subprotocols; the server selects only `agent-os`, so the token is not placed in
a query string or echoed in the response.

Policy implementations are trusted code. They should be deterministic for the same
proposal and context and should use `deny` for errors that cannot be safely recovered.

## Skill packages

A package is trusted local Python code with this exact layout:

```text
my_skill/
├── manifest.toml
└── handlers.py
```

```toml
[skill]
name = "my-skill-package"
version = "1.0.0"

[[skill.handlers]]
match = ["hello", "hi"]
entrypoint = "handlers:hello"
```

```python
# handlers.py
def hello(name: str = "world") -> str:
    return f"Hello, {name}"
```

Load it with stable imports:

```python
from pathlib import Path
from agent_os.api import SkillPackageLoader, SkillRegistry

skills = SkillRegistry()
SkillPackageLoader(skills).load_package(Path("my_skill"))
result = skills.get("hello").invoke({"name": "Ada"})
```

`name` and `version` are required. There must be at least one handler. Every handler
needs a non-empty `match` list and a package-relative `module:function` entrypoint.
The first match is canonical and the rest are aliases. Handlers are either LangChain
`BaseTool` instances or plain callables invoked with keyword arguments. Malformed
packages raise `ValueError` containing the manifest path; duplicate names and aliases
are rejected by `SkillRegistry`. Loading executes Python code, so install packages only
from trusted sources.

## Typing and compatibility

The distribution includes `py.typed`. Type annotations are part of the v2 public
contract; use a Python type checker against `agent_os.api`, but retain runtime error
handling for third-party implementations. Async protocol variants, dependency
installation, remote package discovery, graph internals, CLI/HTTP internals, and
concrete built-in connectors are not stable extension APIs.
