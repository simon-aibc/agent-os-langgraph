# agent-os-langgraph

Agent OS built with LangGraph.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Prerequisites
- Python >= 3.11

## Installation
```bash
python -m pip install -e ".[dev]"
```

## Testing
```bash
python -m pytest tests/
```

## Flow

**R7a Cascading Tool Flow**:
New tasks pass through the tool dispatcher before agent escalation. Plans still
pause for human approval before the executor can run:
```text
START → planner → supervisor → tool_dispatcher
                                  ├─ tool selected → END
                                  └─ escalate → supervisor → architect → human_gate
                                      ⇢ supervisor → executor → supervisor → END
```

## Tool Routing

The dispatcher uses three progressively more expensive tiers:

1. Tier 1 parses an explicit native command deterministically without an LLM.
2. Tier 2 uses the `LLM_ROUTER` model to return a structured tool decision.
3. Tier 3 sends decisions below `0.70` confidence back to the supervisor.

Tier-1 commands use these formats:

```text
read <relative_path>
write <relative_path> :: <content>
bash <command and arguments>
```

The registry is injectable and extensible at runtime:

```python
from agent_os.skills import RegisteredSkill, SkillRegistry

registry = SkillRegistry()
registry.register(
    RegisteredSkill(
        name="summarize",
        aliases=["summary"],
        handler=lambda text: text[:100],
    )
)
```

Filesystem, CodeGraph, and gbrain MCP integrations are intentionally deferred
to R7b; `langchain-mcp-adapters` is not required by R7a.

**Recursion Limit**:
The default recursion limit is 7. `build_runtime_config()` applies this bound
and the thread ID required by the default checkpointer:
```python
from agent_os.graph import graph
from agent_os.routing import build_runtime_config

config = build_runtime_config("my-thread-id")
graph.invoke(state, config=config)
```

## State and Threading
Every invocation of the default compiled graph must provide a non-empty
`configurable.thread_id`. Use a unique ID per independent workflow and reuse
that ID when resuming an interrupted workflow. A recommended scheme is one
thread per user task using `<user>-<UTC timestamp>-<slug>`, for example
`simon-20260801T143000Z-add-logging`.

R6 stores checkpoints in SQLite at `AGENT_OS_CHECKPOINTS_DB` (default:
`./checkpoints.db`). Rebuilding the graph in a new process with the same
database path and thread ID restores the paused workflow:

```python
from langgraph.types import Command

from agent_os.graph import build_graph
from agent_os.routing import build_runtime_config

config = build_runtime_config("simon-20260801T143000Z-add-logging")

# Process A pauses at human_gate and then exits.
build_graph().invoke(state, config=config)

# Process B starts later and resumes from SQLite.
result = build_graph().invoke(Command(resume="approved"), config=config)
```

Tests may inject `InMemorySaver` through `build_graph(checkpointer=...)` when
cross-process durability is not under test.

## Security Caveats
- Never commit `checkpoints.db` or its WAL files. Checkpoints can contain task
  text, messages, plans, human feedback, and other sensitive workflow state.
- `AGENT_OS_SANDBOX` enforces directory paths, not container-level executable
  isolation. Use a container for untrusted models or commands.
- Bash subprocess output is currently unbounded and needs a size cap for
  production environments.
