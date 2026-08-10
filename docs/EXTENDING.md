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
