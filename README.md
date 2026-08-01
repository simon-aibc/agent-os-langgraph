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

**R2 Dynamic Routing**:
The system routes dynamically from the supervisor node based on the current state:
`START → planner → supervisor → [architect | executor | tool_dispatcher | END]`

**Recursion Limit**:
The default recursion limit is 6. You can pass this via runtime config when invoking the graph:
```python
from agent_os.routing import DEFAULT_RUNTIME_CONFIG

graph.invoke(state, DEFAULT_RUNTIME_CONFIG)
```
