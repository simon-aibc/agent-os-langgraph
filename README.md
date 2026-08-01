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

**R5 Human Approval Flow**:
The supervisor dynamically routes work, while implementation plans pause for
human approval before the executor can run:
```text
START → planner → supervisor → architect → human_gate
                                      ⇢ supervisor → executor → supervisor → END
```

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
that ID when resuming an interrupted workflow. R5 uses `InMemorySaver`, so
checkpoints exist only for the lifetime of the process. Callers may pass a
different checkpointer to `build_graph(checkpointer=...)`; durable SQLite
persistence is deferred to R6.

## Security Caveats (R5)
- `AGENT_OS_SANDBOX` enforces directory paths, not container-level executable
  isolation. Use a container for untrusted models or commands.
- Bash subprocess output is currently unbounded and needs a size cap for
  production environments.
