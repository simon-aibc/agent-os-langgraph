import pytest
from fastapi.testclient import TestClient

from agent_os.server.api import app

client = TestClient(app)

def test_api_sessions_list(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv("CHECKPOINT_DB_ENV", db_path)
    
    # Insert a session
    from agent_os.sessions import upsert_session
    upsert_session("thr1", "Test session")
    
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["thread_id"] == "thr1"
    assert data[0]["title"] == "Test session"
    assert "created_at" in data[0]

def test_api_brief(monkeypatch):
    def mock_generate_brief(*args, **kwargs):
        return "Mock brief content"
    
    monkeypatch.setattr("agent_os.server.api.generate_brief", mock_generate_brief)
    
    resp = client.post("/api/brief")
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert data["content"] == "Mock brief content"

def test_api_graph_shape():
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)

@pytest.mark.anyio
async def test_ws_chat_streams(monkeypatch, tmp_path):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv("CHECKPOINT_DB_ENV", db_path)
    
    # Mock graph building and running
    class MockGraph:
        async def astream_events(self, state_update, config, version):
            from langchain_core.messages import AIMessageChunk
            yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="Hel")}}
            yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="lo")}}
            
    def mock_build_graph(checkpointer=None):
        return MockGraph()

    monkeypatch.setattr("agent_os.graph.build_graph", mock_build_graph)
    
    with client.websocket_connect("/api/chat/thr_ws") as websocket:
        websocket.send_text("Hi there")
        
        # Should receive stream tokens then done
        msg1 = websocket.receive_json()
        assert msg1["type"] == "token"
        assert msg1["content"] == "Hel"
        
        msg2 = websocket.receive_json()
        assert msg2["type"] == "token"
        assert msg2["content"] == "lo"
        
        msg3 = websocket.receive_json()
        assert msg3["type"] == "done"

def test_serve_missing_extra(monkeypatch, capsys):
    import asyncio

    # Hide fastapi temporarily
    import sys

    from agent_os.cli.app import async_main
    monkeypatch.setitem(sys.modules, "fastapi", None)
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    
    exit_code = asyncio.run(async_main(["serve"]))
    assert exit_code == 1
    
    captured = capsys.readouterr()
    assert "FastAPI dependencies not installed" in captured.out
    assert "pip install agent-os-langgraph[serve]" in captured.out

def test_bind_localhost_default():
    from agent_os.cli.app import build_parser
    parser = build_parser()
    args = parser.parse_args(["serve"])
    assert args.host == "127.0.0.1"
    assert args.port == 4680
