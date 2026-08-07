import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from agent_os.sandbox import resolve_sandbox_path
from agent_os.schemas import ExecutionResult


class Connector(Protocol):
    """
    A Connector is a tool wrapper that encapsulates logic and context for a specific domain.
    """
    @property
    def name(self) -> str:
        ...

    def capabilities(self) -> dict[str, Any]:
        ...

    def describe_side_effect(self, action: str) -> str:
        ...

    def invoke(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        ...


class MemoryConnector(Protocol):
    """
    A MemoryConnector provides reading capabilities to search, read, and list notes.
    """
    @property
    def name(self) -> str:
        ...

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        ...

    def read_note(self, slug_or_path: str) -> dict[str, Any]:
        ...

    def list_notes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, Connector | MemoryConnector] = {}

    def register(self, name: str, connector: Connector | MemoryConnector) -> None:
        if name in self._connectors:
            raise ValueError(f"Connector '{name}' is already registered.")
        self._connectors[name] = connector

    def resolve(self, name: str) -> Connector | MemoryConnector:
        if name not in self._connectors:
            raise ValueError(f"Connector '{name}' not found in registry.")
        return self._connectors[name]

    def list_connectors(self) -> list[str]:
        return list(self._connectors.keys())


class FilesystemConnector(Connector):
    @property
    def name(self) -> str:
        return "filesystem"

    def capabilities(self) -> dict[str, Any]:
        return {
            "actions": ["read", "list", "stat"]
        }

    def describe_side_effect(self, action: str) -> str:
        return "read"

    def invoke(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        if action not in ["read", "list", "stat"]:
            return ExecutionResult(status="failed", errors=[f"Unsupported action: {action}"])
        
        path = args.get("path")
        if not path:
            return ExecutionResult(status="failed", errors=["Missing argument: path"])
        
        try:
            resolved = resolve_sandbox_path(path)
        except ValueError as e:
            return ExecutionResult(status="failed", errors=[str(e)])
        
        try:
            if action == "read":
                content = resolved.read_text(encoding="utf-8")
                return ExecutionResult(status="completed", outputs={"content": content})
            elif action == "list":
                items = [p.name for p in resolved.iterdir()]
                return ExecutionResult(status="completed", outputs={"items": items})
            elif action == "stat":
                st = resolved.stat()
                return ExecutionResult(status="completed", outputs={"size": st.st_size, "is_dir": resolved.is_dir()})
        except Exception as e:
            return ExecutionResult(status="failed", errors=[f"Filesystem error: {str(e)}"])
        
        return ExecutionResult(status="failed", errors=["Unknown error"])


class MarkdownVaultConnector(MemoryConnector):
    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        
    @property
    def name(self) -> str:
        return "markdown_vault"
        
    def _parse_frontmatter(self, content: str) -> dict[str, Any]:
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}
        fm = match.group(1)
        res = {}
        for line in fm.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                res[k.strip()] = v.strip()
        return res

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        results = []
        for p in self.root_path.rglob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    results.append({"path": p.relative_to(self.root_path).as_posix(), "snippet": content[:100]})
                    if len(results) >= limit:
                        break
            except Exception:
                continue
        return results

    def read_note(self, slug_or_path: str) -> dict[str, Any]:
        path = self.root_path / slug_or_path
        if not path.name.endswith(".md"):
            path = path.with_suffix(".md")
            
        try:
            content = path.read_text(encoding="utf-8")
            fm = self._parse_frontmatter(content)
            
            # Follow basic wikilinks `[[Link]]`
            links = re.findall(r"\[\[(.*?)\]\]", content)
            
            return {"path": slug_or_path, "content": content, "frontmatter": fm, "links": links}
        except FileNotFoundError as e:
            raise ValueError(f"Note not found: {slug_or_path}") from e

    def list_notes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        results = []
        for p in self.root_path.rglob("*.md"):
            results.append({"path": p.relative_to(self.root_path).as_posix()})
        return results


class GbrainConnector(MemoryConnector):
    def __init__(self):
        self.url = os.getenv("GBRAIN_URL", "http://localhost:3131/mcp")
        self.token = os.getenv("GBRAIN_TOKEN")
        
    @property
    def name(self) -> str:
        return "gbrain"
        
    def _call_rpc(self, method: str, params: dict[str, Any]) -> Any:
        if not self.token:
            raise RuntimeError("gbrain not configured")
            
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }).encode("utf-8")
        
        req = urllib.request.Request(self.url, data=payload, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json"
        }, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode("utf-8")
                # Parse SSE if applicable
                for line in content.split("\n"):
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if "result" in data:
                                return data["result"]
                        except json.JSONDecodeError:
                            pass
                
                # Direct JSON fallback
                try:
                    data = json.loads(content)
                    if "result" in data:
                        return data["result"]
                except json.JSONDecodeError:
                    pass
                return content
        except urllib.error.URLError as e:
            raise RuntimeError(f"Gbrain error: {e}") from e

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        res = self._call_rpc("tools/call", {"name": "query", "arguments": {"query": query, "limit": limit}})
        # gbrain returns: {"content": [{"text": "<json string with .hits>"}]}
        if isinstance(res, dict):
            content = res.get("content") or []
            if content and isinstance(content, list):
                text = content[0].get("text", "")
                try:
                    import json
                    nested = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return []
                hits = nested.get("hits") if isinstance(nested, dict) else nested
                return hits if isinstance(hits, list) else []
        return res if isinstance(res, list) else []

    def read_note(self, slug_or_path: str) -> dict[str, Any]:
        res = self._call_rpc("tools/call", {"name": "read_note", "arguments": {"path": slug_or_path}})
        return res if isinstance(res, dict) else {}

    def list_notes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        res = self._call_rpc("tools/call", {"name": "list_notes", "arguments": {"filters": filters or {}}})
        return res if isinstance(res, list) else []
