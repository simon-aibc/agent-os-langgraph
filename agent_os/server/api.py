import datetime
import os
import sqlite3
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from agent_os.brief import generate_brief
from agent_os.checkpoints import CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB
from agent_os.connectors import MarkdownVaultConnector
from agent_os.sandbox import get_sandbox_root
from agent_os.sessions import delete_session, list_sessions

app = FastAPI(title="agent-os API", version="1.6.0")

@app.get("/api/health")
def health_check() -> dict[str, Any]:
    return {"status": "ok", "version": "1.6.0"}

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
    vault_path = os.getenv("AGENT_OS_VAULT_PATH", str(get_sandbox_root().resolve()))
    connector = MarkdownVaultConnector(vault_path)
    sessions = list_sessions()
    date_str = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    
    def invoke_summarizer(prompt: str) -> str:
        # Same proven path as architect.py `_summarizer_fn`: a cli/ backend
        # goes through the CLI architect invoker, otherwise the architect LLM.
        # (resolve_backend_binding().architect is a backend-name string, not an
        # invokable — calling .invoke on it would crash at runtime.)
        model_str = os.getenv("LLM_ARCHITECT", "") or "cli/claude-code"
        if model_str.startswith("cli/"):
            from agent_os.agents.cli_architect import build_cli_architect_invoker
            invoker = build_cli_architect_invoker(model_str[4:])
            return invoker({"task": prompt, "messages": []}).summary
        from langchain_core.messages import HumanMessage

        from agent_os.llm import get_architect_llm
        return str(get_architect_llm(model_str).invoke([HumanMessage(content=prompt)]).content)
        
    brief_md = generate_brief(connector, sessions, date_str, summarizer=invoke_summarizer)
    return {"date": date_str, "content": brief_md}

@app.get("/api/graph")
def get_graph_data() -> dict[str, list[dict[str, Any]]]:
    # Phase this: returning raw graph shape
    return {"nodes": [], "edges": []}

@app.websocket("/api/chat/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str) -> None:
    await websocket.accept()
    import json

    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from agent_os.graph import build_graph
    
    db_path = os.getenv(CHECKPOINT_DB_ENV, DEFAULT_CHECKPOINT_DB)
    
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        graph = build_graph(checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            while True:
                data = await websocket.receive_text()
                # Run graph
                state_update = {"messages": [HumanMessage(content=data)]}
                
                async for event in graph.astream_events(state_update, config, version="v1"):
                    if event["event"] == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        if chunk.content:
                            await websocket.send_text(json.dumps({"type": "token", "content": chunk.content}))
                await websocket.send_text(json.dumps({"type": "done"}))
                
        except WebSocketDisconnect:
            pass
