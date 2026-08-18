import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

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


@dataclass
class MemoryWriteResult:
    ref: str
    mode: str                # "create" | "append" | "overwrite"
    bytes_written: int | None
    committed: bool
    # A policy rejection is not an I/O exception, but callers still need a
    # machine-readable way to distinguish it from a successful write.  Native
    # connectors leave these defaults intact; the memory gate fills them from
    # the policy execution result when a write never reaches the connector.
    status: Literal["completed", "failed", "cancelled"] = "completed"
    error: str | None = None

class WritableMemory(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def supported_write_modes(self) -> frozenset[str]: ...
    def write_note(
        self,
        ref: str,
        content: str,
        frontmatter: dict[str, Any] | None = None,
        mode: Literal["create", "append", "overwrite"] = "create",
    ) -> MemoryWriteResult: ...
    def describe_write_side_effect(self, ref: str, mode: str) -> str: ...


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, Any] = {}

    def register(self, name: str, connector: Any) -> None:
        if name in self._connectors:
            raise ValueError(f"Connector '{name}' is already registered.")
        self._connectors[name] = connector

    def resolve(self, name: str) -> Any:
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


def _parse_frontmatter(content: str) -> dict[str, Any]:
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

def _serialize_markdown_with_frontmatter(content: str, frontmatter: dict[str, Any]) -> str:
    if not frontmatter:
        return content
    fm_lines = ["---"]
    for k, v in frontmatter.items():
        fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(content)
    return "\n".join(fm_lines)

class MarkdownVaultConnector(MemoryConnector):
    supported_write_modes = frozenset({"append", "create", "overwrite"})

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        
    @property
    def name(self) -> str:
        return "markdown_vault"
        
    def describe_write_side_effect(self, ref: str, mode: str) -> str:
        if mode == "append":
            return f"append to note '{ref}' (creates if missing)"
        elif mode == "overwrite":
            return f"OVERWRITE note '{ref}' — existing content lost"
        return f"create note '{ref}'"

    def write_note(
        self,
        ref: str,
        content: str,
        frontmatter: dict[str, Any] | None = None,
        mode: Literal["create", "append", "overwrite"] = "create",
    ) -> MemoryWriteResult:
        path = self.root_path / ref
        if not path.name.endswith(".md"):
            path = path.with_suffix(".md")
            
        try:
            path = path.resolve()
            path.relative_to(self.root_path)
        except ValueError as e:
            raise ValueError(f"Path traversal detected: {ref}") from e
            
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if mode == "create" and path.exists():
            raise FileExistsError(f"Note already exists: {ref}")
            
        final_content = content
        if mode in ("create", "overwrite") and frontmatter:
            final_content = _serialize_markdown_with_frontmatter(content, frontmatter)
            
        if mode == "append":
            file_exists = path.exists() and path.stat().st_size > 0
            with open(path, "a", encoding="utf-8") as f:
                if file_exists:
                    bytes_written = f.write("\n" + final_content)
                else:
                    bytes_written = f.write(final_content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                bytes_written = f.write(final_content)
                
        return MemoryWriteResult(
            ref=path.relative_to(self.root_path).as_posix(),
            mode=mode,
            bytes_written=bytes_written,
            committed=True
        )

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        results = []
        for p in self.root_path.rglob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    fm = _parse_frontmatter(content)
                    title = fm.get("title")
                    if not title:
                        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                        title = h1_match.group(1).strip() if h1_match else None
                    
                    results.append({
                        "ref": p.relative_to(self.root_path).as_posix(),
                        "title": title,
                        "snippet": content[:100],
                        "score": None
                    })
                    if len(results) >= limit:
                        break
            except Exception:
                continue
        return results

    def read_note(self, ref: str) -> dict[str, Any]:
        path = self.root_path / ref
        if not path.name.endswith(".md"):
            path = path.with_suffix(".md")
            
        try:
            content = path.read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            
            # Follow basic wikilinks `[[Link]]`
            links = re.findall(r"\[\[(.*?)\]\]", content)
            
            return {"ref": ref, "content": content, "frontmatter": fm, "links": links}
        except FileNotFoundError as e:
            raise ValueError(f"Note not found: {ref}") from e

    def list_notes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        results = []
        for p in self.root_path.rglob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                fm = _parse_frontmatter(content)
                title = fm.get("title")
                if not title:
                    h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                    title = h1_match.group(1).strip() if h1_match else None
            except Exception:
                title = None
            results.append({"ref": p.relative_to(self.root_path).as_posix(), "title": title})
        return results


class GbrainConnector(MemoryConnector):
    # Gbrain currently exposes only ``put_page``, an unconditional upsert.
    # Do not map the safer create/append vocabulary onto that destructive
    # primitive; callers must explicitly request overwrite instead.
    supported_write_modes = frozenset({"overwrite"})

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
        
        hits = []
        if isinstance(res, dict):
            c_list = res.get("content") or []
            if c_list and isinstance(c_list, list):
                text = c_list[0].get("text", "")
                try:
                    import json
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and "hits" in parsed:
                        hits = parsed["hits"]
                    elif isinstance(parsed, list):
                        hits = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
        elif isinstance(res, list):
            hits = res
            
        results = []
        if isinstance(hits, list):
            for hit in hits:
                if isinstance(hit, dict):
                    results.append({
                        "ref": hit.get("slug", ""),
                        "title": hit.get("title"),
                        "snippet": hit.get("chunk_text", "")[:200],
                        "score": hit.get("score")
                    })
        return results

    def read_note(self, ref: str) -> dict[str, Any]:
        res = self._call_rpc("tools/call", {"name": "get_page", "arguments": {"slug": ref}})
        
        content = ""
        fm: dict[str, Any] = {}
        if isinstance(res, dict):
            c_list = res.get("content") or []
            if c_list and isinstance(c_list, list):
                text = c_list[0].get("text", "")
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        content = parsed.get("compiled_truth") or parsed.get("content", "")
                        # gbrain hoists `title` and stores remaining frontmatter keys
                        # as a top-level `frontmatter` dict; compiled_truth is body-only,
                        # so parse from those fields, not from the (stripped) body.
                        fm = dict(parsed.get("frontmatter") or {})
                        if parsed.get("title"):
                            fm.setdefault("title", parsed["title"])
                    else:
                        content = text
                except (json.JSONDecodeError, TypeError):
                    content = text
        elif isinstance(res, str):
            content = res

        if not fm:
            # Fallback: raw markdown body (non-gbrain-shaped response)
            fm = _parse_frontmatter(content)
        links = re.findall(r"\[\[(.*?)\]\]", content)
        
        return {
            "ref": ref,
            "content": content,
            "frontmatter": fm,
            "links": links
        }

    def list_notes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        res = self._call_rpc("tools/call", {"name": "list_pages", "arguments": filters or {}})
        
        pages = []
        if isinstance(res, dict):
            c_list = res.get("content") or []
            if c_list and isinstance(c_list, list):
                text = c_list[0].get("text", "")
                try:
                    import json
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and "pages" in parsed:
                        pages = parsed["pages"]
                    elif isinstance(parsed, list):
                        pages = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
        elif isinstance(res, list):
            pages = res
            
        results = []
        if isinstance(pages, list):
            for page in pages:
                if isinstance(page, dict):
                    results.append({
                        "ref": page.get("slug", ""),
                        "title": page.get("title")
                    })
        return results

    def describe_write_side_effect(self, ref: str, mode: str) -> str:
        if mode == "overwrite":
            return f"OVERWRITE gbrain page '{ref}' via put_page upsert"
        return (
            f"Gbrain does not support safe {mode} for '{ref}'; "
            "its available write primitive is an upsert"
        )

    def write_note(
        self,
        ref: str,
        content: str,
        frontmatter: dict[str, Any] | None = None,
        mode: Literal["create", "append", "overwrite"] = "create",
    ) -> MemoryWriteResult:
        if mode != "overwrite":
            raise NotImplementedError(
                "GbrainConnector only supports explicit overwrite: its put_page "
                "operation is an upsert and cannot safely implement create or append."
            )
            
        if not ref.startswith("agentos/"):
            ref = f"agentos/{ref}"
            
        merged_fm = {}
        if frontmatter:
            merged_fm.update(frontmatter)
            
        import datetime
        now = datetime.datetime.now(datetime.UTC).isoformat()
        
        merged_fm.setdefault("agent", "agent-os")
        merged_fm.setdefault("created", now)
        merged_fm.setdefault("via", "agent-os-v1.4")
        merged_fm.setdefault("source", "default")
        
        final_content = _serialize_markdown_with_frontmatter(content, merged_fm)
        
        self._call_rpc("tools/call", {"name": "put_page", "arguments": {"slug": ref, "content": final_content}})
        
        return MemoryWriteResult(
            ref=ref,
            mode=mode,
            bytes_written=len(final_content.encode("utf-8")),
            committed=True
        )
