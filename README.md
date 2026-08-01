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

**R7a/R7b Cascading Tool Flow**:
New tasks pass through the tool dispatcher before agent escalation. Plans still
pause for human approval before the executor can run:
```text
START → planner → supervisor → tool_dispatcher
                                  ├─ Tier 1/Tier 2 success → END
                                  └─ Tier 3 escalation → supervisor → architect
                                      → human_gate → supervisor → executor
                                      → supervisor → END
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

### MCP Tool Ecosystem

The registry combines three native tools with three optional MCP sources. Each
MCP server may expose several tools; loaded names are prefixed as
`mcp_<server>_<tool>` to avoid collisions.

| Source | Kind | Capability |
|---|---|---|
| `read_file` | Native tool | Read a sandboxed file |
| `write_file` | Native tool | Write a sandboxed file |
| `bash` | Native tool | Run a bounded subprocess in the sandbox |
| `filesystem` | MCP server | File operations from `@modelcontextprotocol/server-filesystem` |
| `codegraph` | MCP server | Code intelligence from `codegraph serve --mcp` |
| `gbrain` | MCP server | Tools exposed by an HTTP MCP endpoint |

### MCP Configuration

| Environment variable | Default | Description |
|---|---|---|
| `MCP_FILESYSTEM_ENABLED` | `false` | Enable the stdio filesystem server; requires `AGENT_OS_SANDBOX`. |
| `MCP_CODEGRAPH_ENABLED` | `false` | Enable the local CodeGraph MCP server. |
| `MCP_GBRAIN_URL` | empty | Enable gbrain with an absolute HTTP(S) MCP URL. |
| `AGENT_OS_SANDBOX` | `./sandbox` | Restrict the filesystem server to this root. `/` and the user home directory are rejected. |

### Loading Custom MCP Servers

Applications load remote tools asynchronously, then inject the resulting
synchronous registry into the dispatcher:

```python
import asyncio

from agent_os.default_registry import build_default_registry_with_mcp
from agent_os.graph import build_graph
from agent_os.nodes.tool_dispatcher import build_tool_dispatcher_node

CUSTOM_SERVERS = {
    "docs": {
        "transport": "http",
        "url": "https://mcp.example.com/mcp",
    }
}


async def build_custom_graph():
    registry = await build_default_registry_with_mcp(
        server_configs=CUSTOM_SERVERS,
    )
    dispatcher = build_tool_dispatcher_node(registry=registry)
    return build_graph(tool_dispatcher_node_impl=dispatcher)


graph = asyncio.run(build_custom_graph())
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

To run real, opt-in MCP integration tests (requires appropriate local servers):
```shell
MCP_FILESYSTEM_ENABLED=true \
AGENT_OS_SANDBOX=./sandbox \
python -m pytest -m integration tests/test_mcp_integration.py
```

## Security Caveats
- Never commit `checkpoints.db` or its WAL files. Checkpoints can contain task
  text, messages, plans, human feedback, and other sensitive workflow state.
- `AGENT_OS_SANDBOX` enforces directory paths, not container-level executable
  isolation. Use a container for untrusted models or commands.
- stdio servers execute local binaries. For example, enabling the filesystem
  server runs `npx` in the local process environment.
- The filesystem MCP server is restricted to `AGENT_OS_SANDBOX`; other stdio
  servers must be trusted not to execute arbitrary OS commands.
- Enabled MCP servers extend the agent's trust boundary. Only configure URLs
  or packages from trusted publishers.
- Bash subprocess output is currently unbounded and needs a size cap for
  production environments.
