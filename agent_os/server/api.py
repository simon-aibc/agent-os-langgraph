import asyncio
import hmac
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB
from agent_os.connectors import MemoryConnector
from agent_os.public_concierge import (
    PublicChatRequest,
    PublicChatResponse,
    list_public_leads,
    load_public_concierge_profile,
)
from agent_os.public_concierge_ai import (
    PublicConciergeAI,
    public_concierge_runtime_summary,
)
from agent_os.runs import (
    append_event,
    create_run,
    get_run,
    list_events,
    list_runs,
    set_status,
    transition_status,
)
from agent_os.sandbox import resolve_workspace_root
from agent_os.schedule_models import ScheduleInput
from agent_os.scheduler import SchedulerService
from agent_os.server.run_executor import execute_run
from agent_os.server.runtime import (
    build_runtime_graph,
    initial_state,
    memory_connector,
    package_version,
    runtime_config,
    runtime_summary,
)
from agent_os.sessions import delete_session, list_sessions


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start/stop the scheduler service around the app lifetime."""
    scheduler = SchedulerService()
    app.state.scheduler = scheduler
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


SERVER_VERSION = package_version()

app = FastAPI(title="agent-os API", version=SERVER_VERSION, lifespan=_lifespan)

# The Runtime API is meant to be driven by a browser operator console on a
# different localhost port, so cross-origin requests must be allowed. Defaults
# cover the console dev/prod port; override with AGENT_OS_CORS_ORIGINS (comma
# separated) for other origins.
_default_cors = "http://127.0.0.1:4100,http://localhost:4100"
_cors_origins = [
    o.strip()
    for o in os.getenv("AGENT_OS_CORS_ORIGINS", _default_cors).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

TERMINAL_RUN_STATUSES = {"completed", "cancelled", "error"}
GRAPH_MAX_NODES = 200
ACTIVE_RUN_TASKS: dict[str, asyncio.Task[None]] = {}
PUBLIC_CONCIERGE_BUCKETS: dict[str, list[float]] = {}
PUBLIC_CONCIERGE_WINDOW_SECONDS = 60.0


class CreateRunRequest(BaseModel):
    task: str
    thread_id: str | None = None
    workspace: str | None = None


class ApproveRunRequest(BaseModel):
    feedback: str | None = None


def _public_concierge_rate_limit(request: Request) -> None:
    limit = int(os.getenv("AGENT_OS_PUBLIC_CONCIERGE_RATE_LIMIT", "20"))
    if limit <= 0:
        return

    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_key = forwarded_for.split(",", 1)[0].strip()
    if not client_key and request.client is not None:
        client_key = request.client.host
    if not client_key:
        client_key = "unknown"

    now = time.monotonic()
    bucket = [
        ts
        for ts in PUBLIC_CONCIERGE_BUCKETS.get(client_key, [])
        if now - ts < PUBLIC_CONCIERGE_WINDOW_SECONDS
    ]
    if len(bucket) >= limit:
        PUBLIC_CONCIERGE_BUCKETS[client_key] = bucket
        raise HTTPException(status_code=429, detail="Public concierge rate limit exceeded")
    bucket.append(now)
    PUBLIC_CONCIERGE_BUCKETS[client_key] = bucket


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    workspace = runtime_summary()
    return {
        "status": "ok" if workspace.get("status") != "error" else "degraded",
        "version": SERVER_VERSION,
        "workspace": workspace,
        "active_runs": len(ACTIVE_RUN_TASKS),
    }


@app.get("/api/public/concierge/health")
def public_concierge_health() -> dict[str, object]:
    profile = load_public_concierge_profile()
    return {
        "status": "ok" if profile is not None else "not_configured",
        "configured": profile is not None,
        "tenant_id": profile.tenant_id if profile is not None else None,
        **public_concierge_runtime_summary(),
    }


@app.post("/api/public/concierge/chat")
async def public_concierge_chat(
    request: Request,
    payload: PublicChatRequest,
) -> PublicChatResponse:
    profile = load_public_concierge_profile()
    if profile is None:
        raise HTTPException(status_code=404, detail="Public concierge is not configured")
    _public_concierge_rate_limit(request)
    return await asyncio.to_thread(PublicConciergeAI(profile).respond, payload)


@app.get("/api/public/concierge/leads")
def public_concierge_leads(
    request: Request,
    limit: int = 100,
) -> list[dict[str, object]]:
    token = os.getenv("AGENT_OS_PUBLIC_CONCIERGE_ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Public concierge lead review is not configured")
    # This endpoint is intentionally token-gated and should sit behind HTTPS in
    # production. It is for internal review dashboards, not the public website.
    provided = request.headers.get("x-admin-token", "").strip()
    bearer = request.headers.get("authorization", "").strip()
    if bearer.lower().startswith("bearer "):
        provided = bearer[7:].strip()
    if not hmac.compare_digest(provided, token):
        raise HTTPException(status_code=403, detail="Forbidden")
    return list_public_leads(limit=limit)

@app.get("/api/sessions")
def get_sessions() -> list[dict[str, Any]]:
    return list_sessions()

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    from langgraph.checkpoint.sqlite import SqliteSaver
    db_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        saver = SqliteSaver(conn)
        config = {"configurable": {"thread_id": session_id}}
        tup = saver.get_tuple(config)
        if tup is None:
            raise HTTPException(status_code=404, detail="Session not found")
            
        state_vals = tup.checkpoint.get("channel_values", {})
        messages = [{"type": type(m).__name__, "content": m.content} for m in state_vals.get("messages", [])]
        state = {k: v for k, v in state_vals.items() if k != "messages"}
        return {"id": session_id, "messages": messages, "state": state}
    finally:
        if 'conn' in locals():
            conn.close()

@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str, confirm: bool = False) -> dict[str, str]:
    if not confirm:
        raise HTTPException(status_code=400, detail="Missing confirm=true")
    from langgraph.checkpoint.sqlite import SqliteSaver
    db_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        saver = SqliteSaver(conn)
        # Assuming delete_thread exists on SqliteSaver in this setup, or we just rely on delete_session
        try:
            # LangGraph might not have delete_thread sync method on all backends, let's just ignore if not present
            if hasattr(saver, "delete_thread"):
                saver.delete_thread(session_id)
        except Exception:
            pass
        delete_session(session_id)
        return {"status": "deleted", "id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if 'conn' in locals():
            conn.close()

@app.post("/api/brief")
@app.get("/api/brief")
def create_brief() -> dict[str, str]:
    from agent_os.brief_runtime import execute_brief

    res = execute_brief(write=False)
    return {"date": res.date, "content": res.content}

def build_graph_data(
    connector: MemoryConnector,
    max_nodes: int,
) -> dict[str, list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    for note in connector.list_notes()[: max(max_nodes, 0)]:
        ref = note.get("ref")
        if not ref:
            continue

        title = note.get("title")
        nodes.append(
            {
                "id": ref,
                "title": title or ref,
                "group": ref.split("/")[0] if "/" in ref else "",
                "type": "page",
            }
        )

    refs = {node["id"] for node in nodes}
    title_to_ref = {
        node["title"]: node["id"]
        for node in nodes
        if node["title"] and node["title"] != node["id"]
    }

    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    for node in nodes:
        source = node["id"]
        try:
            note = connector.read_note(source)
        except Exception:
            continue

        for link in note.get("links") or []:
            target = link if link in refs else title_to_ref.get(link)
            if target not in refs or target == source:
                continue

            edge_key = (source, target)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append({"source": source, "target": target, "type": "link"})

    return {"nodes": nodes, "edges": edges}


@app.get("/api/graph")
def get_graph_data(limit: int = GRAPH_MAX_NODES) -> dict[str, list[dict[str, Any]]]:
    try:
        effective_max = min(max(limit, 0), GRAPH_MAX_NODES)
        return build_graph_data(memory_connector(), effective_max)
    except Exception:
        return {"nodes": [], "edges": []}


def _start_run_task(
    run_id: str,
    thread_id: str,
    task: str,
    *,
    resume_feedback: str | None = None,
) -> None:
    existing = ACTIVE_RUN_TASKS.get(run_id)
    if existing is not None and not existing.done():
        return

    async def runner() -> None:
        try:
            await execute_run(
                run_id,
                thread_id,
                task,
                resume_feedback=resume_feedback,
            )
        except asyncio.CancelledError:
            run = get_run(run_id)
            if run is not None and run["status"] not in TERMINAL_RUN_STATUSES:
                set_status(run_id, "cancelled", ended=True)
                append_event(run_id, "status", {"status": "cancelled"})
            raise
        finally:
            ACTIVE_RUN_TASKS.pop(run_id, None)

    ACTIVE_RUN_TASKS[run_id] = asyncio.create_task(
        runner(),
        name=f"agent-os-run-{run_id}",
    )


@app.post("/api/runs")
async def create_run_endpoint(request: CreateRunRequest) -> dict[str, str]:
    try:
        workspace = str(resolve_workspace_root(request.workspace))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    thread_id = request.thread_id or str(uuid.uuid4())
    run_id = create_run(thread_id, workspace, request.task)
    _start_run_task(run_id, thread_id, request.task)
    return {"run_id": run_id, "thread_id": thread_id, "status": "queued"}

@app.get("/api/runs")
def list_runs_endpoint(
    status: str | None = None,
    workspace: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return list_runs(status=status, workspace=workspace, limit=limit)

def _latest_interrupt_prompt(run_id: str) -> object | None:
    for event in reversed(list_events(run_id)):
        if event["kind"] == "interrupt":
            payload = event["payload"]
            if isinstance(payload, dict):
                return payload.get("prompt")
            return payload
    return None

@app.get("/api/runs/{run_id}")
def get_run_endpoint(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run["interrupt"] = (
        _latest_interrupt_prompt(run_id)
        if run["status"] == "interrupted"
        else None
    )
    return run

@app.post("/api/runs/{run_id}/approve")
async def approve_run_endpoint(
    run_id: str,
    request: ApproveRunRequest,
) -> dict[str, str]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] != "interrupted":
        if run["status"] == "running":
            return {"run_id": run_id, "status": "running"}
        raise HTTPException(status_code=409, detail="Run is not interrupted")

    if not transition_status(run_id, expected="interrupted", status="running"):
        latest = get_run(run_id)
        if latest is not None and latest["status"] == "running":
            return {"run_id": run_id, "status": "running"}
        raise HTTPException(status_code=409, detail="Run is not interrupted")
    _start_run_task(
        run_id,
        run["thread_id"],
        "",
        resume_feedback=request.feedback or "",
    )
    return {"run_id": run_id, "status": "running"}

@app.post("/api/runs/{run_id}/cancel")
async def cancel_run_endpoint(run_id: str) -> dict[str, str]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] in TERMINAL_RUN_STATUSES:
        raise HTTPException(status_code=409, detail="Run is already terminal")

    active_task = ACTIVE_RUN_TASKS.get(run_id)
    if active_task is not None and not active_task.done():
        active_task.cancel()
    set_status(run_id, "cancelled", ended=True)
    append_event(run_id, "status", {"status": "cancelled"})
    return {"run_id": run_id, "status": "cancelled"}

@app.get("/api/runs/{run_id}/events")
def get_run_events(run_id: str, after: int = 0) -> StreamingResponse:
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_stream():
        last_seq = after
        for event in list_events(run_id, after=last_seq):
            last_seq = event["seq"]
            yield f"data: {json.dumps(event)}\n\n"

        while True:
            for event in list_events(run_id, after=last_seq):
                last_seq = event["seq"]
                yield f"data: {json.dumps(event)}\n\n"

            run = get_run(run_id)
            if run is None or run["status"] in TERMINAL_RUN_STATUSES:
                yield "event: end\ndata: {}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")



@app.get("/api/schedules")
def list_schedules_endpoint(
    kind: str | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    from agent_os.schedules import list_schedules

    return list_schedules(kind=kind, enabled=enabled)


@app.post("/api/schedules", status_code=201)
def create_schedule_endpoint(request: ScheduleInput) -> dict[str, Any]:
    from agent_os.schedules import create_schedule, get_schedule

    try:
        sid = create_schedule(
            name=request.name,
            kind=request.kind,
            trigger_kind=request.trigger_kind,
            trigger_value=request.trigger_value,
            timezone=request.timezone,
            payload=request.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    sched = get_schedule(sid)
    if sched is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve created schedule")
    return sched


@app.websocket("/api/chat/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str) -> None:
    await websocket.accept()
    import json

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
    
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        graph = build_runtime_graph(checkpointer=saver)
        config = runtime_config(thread_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                # Run graph
                state_update = initial_state(data)
                
                async for event in graph.astream_events(state_update, config, version="v1"):
                    if event["event"] == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        if chunk.content:
                            await websocket.send_text(json.dumps({"type": "token", "content": chunk.content}))
                await websocket.send_text(json.dumps({"type": "done"}))
                
        except WebSocketDisconnect:
            pass
