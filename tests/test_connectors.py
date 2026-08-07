import json
from unittest.mock import MagicMock, patch

import pytest

from agent_os.connectors import (
    ConnectorRegistry,
    FilesystemConnector,
    GbrainConnector,
    MarkdownVaultConnector,
)


def test_connector_registry():
    registry = ConnectorRegistry()
    fs = FilesystemConnector()
    registry.register(fs.name, fs)
    
    assert registry.list_connectors() == ["filesystem"]
    assert registry.resolve("filesystem") == fs
    
    with pytest.raises(ValueError, match="already registered"):
        registry.register("filesystem", fs)
        
    with pytest.raises(ValueError, match="not found in registry"):
        registry.resolve("non_existent")


def test_filesystem_connector(monkeypatch, tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("AGENT_OS_SANDBOX", str(sandbox))
    
    (sandbox / "test.txt").write_text("hello world")
    
    fs = FilesystemConnector()
    
    # test read
    res = fs.invoke("read", {"path": "test.txt"})
    assert res.status == "completed"
    assert res.outputs["content"] == "hello world"
    
    # test list
    res = fs.invoke("list", {"path": "."})
    assert res.status == "completed"
    assert "test.txt" in res.outputs["items"]
    
    # test unsupported
    res = fs.invoke("write", {"path": "test.txt"})
    assert res.status == "failed"
    assert "Unsupported action" in res.errors[0]
    
    # test escape
    res = fs.invoke("read", {"path": "../outside.txt"})
    assert res.status == "failed"
    assert "resolves outside the sandbox" in res.errors[0]


def test_markdown_vault_connector(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    
    (vault / "note1.md").write_text("---\ntags: test\n---\nHello [[note2]]")
    (vault / "nested").mkdir()
    (vault / "nested" / "note2.md").write_text("Just a nested note")
    
    md = MarkdownVaultConnector(str(vault))
    
    # list
    notes = md.list_notes()
    paths = [n["path"] for n in notes]
    assert "note1.md" in paths
    assert "nested/note2.md" in paths
    
    # search
    res = md.search("nested")
    assert len(res) == 1
    assert res[0]["path"] == "nested/note2.md"
    
    # read
    note = md.read_note("note1")
    assert note["frontmatter"]["tags"] == "test"
    assert "note2" in note["links"]


def test_gbrain_connector_not_configured(monkeypatch):
    monkeypatch.delenv("GBRAIN_TOKEN", raising=False)
    gbrain = GbrainConnector()
    with pytest.raises(RuntimeError, match="gbrain not configured"):
        gbrain.search("test")


def test_gbrain_connector_configured(monkeypatch):
    monkeypatch.setenv("GBRAIN_TOKEN", "test-token")
    monkeypatch.setenv("GBRAIN_URL", "http://test/mcp")
    gbrain = GbrainConnector()
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"result": {"content": [{"text": json.dumps({"hits": [{"path": "remote.md"}]})}]}}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        res = gbrain.search("test")
        assert len(res) == 1
        assert res[0]["path"] == "remote.md"
