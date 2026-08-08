import json

import pytest
from fastapi.testclient import TestClient

from agent_os.checkpoints import CHECKPOINT_DB_ENV
from agent_os.runs import append_event, create_run, get_run, list_events, set_status
from agent_os.server.api import app, build_graph_data

client = TestClient(app)

def test_health_version():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "1.7.2"}

def test_cors_allows_console_origin():
    origin = "http://127.0.0.1:4100"
    resp = client.get("/api/health", headers={"Origin": origin})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin

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

class FakeMemoryConnector:
    @property
    def name(self):
        return "fake"

    def __init__(self):
        self.notes = [
            {"ref": "team/alpha", "title": "Alpha"},
            {"ref": "beta", "title": "Beta Page"},
            {"ref": "gamma", "title": None},
            {"ref": "", "title": "No Ref"},
        ]
        self.reads = {
            "team/alpha": {
                "ref": "team/alpha",
                "content": "",
                "frontmatter": {},
                "links": [
                    "beta",
                    "Beta Page",
                    "Alpha",
                    "missing",
                    "team/alpha",
                ],
            },
            "beta": {
                "ref": "beta",
                "content": "",
                "frontmatter": {},
                "links": ["gamma"],
            },
            "gamma": {
                "ref": "gamma",
                "content": "",
                "frontmatter": {},
                "links": [],
            },
        }

    def search(self, query, limit=10):
        return []

    def list_notes(self, filters=None):
        return self.notes

    def read_note(self, slug_or_path):
        return self.reads[slug_or_path]


def test_build_graph_data_nodes_and_edges():
    data = build_graph_data(FakeMemoryConnector(), 10)

    assert data["nodes"] == [
        {
            "id": "team/alpha",
            "title": "Alpha",
            "group": "team",
            "type": "page",
        },
        {"id": "beta", "title": "Beta Page", "group": "", "type": "page"},
        {"id": "gamma", "title": "gamma", "group": "", "type": "page"},
    ]
    assert data["edges"] == [
        {"source": "team/alpha", "target": "beta", "type": "link"},
        {"source": "beta", "target": "gamma", "type": "link"},
    ]


def test_build_graph_data_respects_node_cap():
    data = build_graph_data(FakeMemoryConnector(), 2)

    assert [node["id"] for node in data["nodes"]] == ["team/alpha", "beta"]
    assert data["edges"] == [
        {"source": "team/alpha", "target": "beta", "type": "link"}
    ]


def test_api_graph_empty_state_fallback(monkeypatch):
    def raise_gbrain_connector():
        raise RuntimeError("gbrain unavailable")

    monkeypatch.setattr("agent_os.server.api.GbrainConnector", raise_gbrain_connector)

    resp = client.get("/api/graph")

    assert resp.status_code == 200
    assert resp.json() == {"nodes": [], "edges": []}

def test_run_events_sse_replays_from_offset_and_ends(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv(CHECKPOINT_DB_ENV, db_path)
    run_id = create_run("thread-sse", "workspace", "task")
    append_event(run_id, "node", {"name": "planner", "event": "on_chain_start"})
    append_event(run_id, "token", {"content": "hello"})
    append_event(run_id, "result", {})
    set_status(run_id, "completed", ended=True)

    resp = client.get(f"/api/runs/{run_id}/events?after=1")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    frames = [frame for frame in resp.text.strip().split("\n\n") if frame]
    replayed = [json.loads(frame.removeprefix("data: ")) for frame in frames[:2]]
    assert [event["seq"] for event in replayed] == [2, 3]
    assert [event["kind"] for event in replayed] == ["token", "result"]
    assert frames[-1] == "event: end\ndata: {}"

def test_run_api_lifecycle_create_interrupt_approve_complete(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv(CHECKPOINT_DB_ENV, db_path)
    calls = []

    async def fake_execute_run(run_id, thread_id, task, *, resume_feedback=None):
        calls.append(
            {
                "run_id": run_id,
                "thread_id": thread_id,
                "task": task,
                "resume_feedback": resume_feedback,
            }
        )
        if resume_feedback is None:
            append_event(run_id, "interrupt", {"prompt": "First prompt"})
            append_event(run_id, "interrupt", {"prompt": "Approve revised plan?"})
            set_status(run_id, "interrupted")
        else:
            append_event(run_id, "result", {})
            set_status(run_id, "completed", ended=True)

    monkeypatch.setattr("agent_os.server.api.execute_run", fake_execute_run)

    create_resp = client.post(
        "/api/runs",
        json={"task": "ship it", "workspace": "workspace-a"},
    )

    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["status"] == "queued"
    assert created["thread_id"]

    interrupted_resp = client.get(f"/api/runs/{created['run_id']}")
    assert interrupted_resp.status_code == 200
    interrupted = interrupted_resp.json()
    assert interrupted["status"] == "interrupted"
    assert interrupted["workspace"] == "workspace-a"
    assert interrupted["interrupt"] == "Approve revised plan?"

    approve_resp = client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"feedback": "approved"},
    )

    assert approve_resp.status_code == 200
    assert approve_resp.json() == {"run_id": created["run_id"], "status": "running"}

    completed_resp = client.get(f"/api/runs/{created['run_id']}")
    assert completed_resp.status_code == 200
    completed = completed_resp.json()
    assert completed["status"] == "completed"
    assert completed["interrupt"] is None
    assert calls == [
        {
            "run_id": created["run_id"],
            "thread_id": created["thread_id"],
            "task": "ship it",
            "resume_feedback": None,
        },
        {
            "run_id": created["run_id"],
            "thread_id": created["thread_id"],
            "task": "",
            "resume_feedback": "approved",
        },
    ]

def test_run_api_cancel_path(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv(CHECKPOINT_DB_ENV, db_path)
    run_id = create_run("thread-cancel", "workspace-a", "task")
    set_status(run_id, "interrupted")

    resp = client.post(f"/api/runs/{run_id}/cancel")

    assert resp.status_code == 200
    assert resp.json() == {"run_id": run_id, "status": "cancelled"}
    run = get_run(run_id)
    assert run["status"] == "cancelled"
    assert run["ended_at"] is not None
    events = list_events(run_id)
    assert events[-1]["kind"] == "status"
    assert events[-1]["payload"] == {"status": "cancelled"}

def test_run_api_404s(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv(CHECKPOINT_DB_ENV, db_path)

    assert client.get("/api/runs/missing").status_code == 404
    assert client.post("/api/runs/missing/approve", json={}).status_code == 404
    assert client.post("/api/runs/missing/cancel").status_code == 404

def test_run_api_approve_conflict_when_not_interrupted(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv(CHECKPOINT_DB_ENV, db_path)
    run_id = create_run("thread-approve-conflict", None, "task")

    resp = client.post(f"/api/runs/{run_id}/approve", json={})

    assert resp.status_code == 409

def test_run_api_cancel_conflict_when_terminal(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv(CHECKPOINT_DB_ENV, db_path)
    run_id = create_run("thread-cancel-conflict", None, "task")
    set_status(run_id, "completed", ended=True)

    resp = client.post(f"/api/runs/{run_id}/cancel")

    assert resp.status_code == 409

def test_run_api_list_filters(tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkpoints.sqlite")
    monkeypatch.setenv(CHECKPOINT_DB_ENV, db_path)
    queued = create_run("thread-queued", "workspace-a", "task")
    running_a = create_run("thread-running-a", "workspace-a", "task")
    running_b = create_run("thread-running-b", "workspace-b", "task")
    set_status(running_a, "running")
    set_status(running_b, "running")

    queued_resp = client.get("/api/runs?status=queued")
    assert queued_resp.status_code == 200
    assert [run["run_id"] for run in queued_resp.json()] == [queued]

    workspace_resp = client.get("/api/runs?workspace=workspace-a")
    assert workspace_resp.status_code == 200
    assert {run["run_id"] for run in workspace_resp.json()} == {queued, running_a}

    filtered_resp = client.get("/api/runs?status=running&workspace=workspace-a")
    assert filtered_resp.status_code == 200
    assert [run["run_id"] for run in filtered_resp.json()] == [running_a]

    limit_resp = client.get("/api/runs?limit=2")
    assert limit_resp.status_code == 200
    assert len(limit_resp.json()) == 2

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
