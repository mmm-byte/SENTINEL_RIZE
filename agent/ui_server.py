"""
SENTINEL SRE Control Cockpit — FastAPI server
=============================================
Endpoints
---------
  GET  /              -> SRE Control Cockpit HTML
  GET  /api/status    -> live status JSON
  POST /api/run       -> trigger a healing run
  POST /api/approve   -> approve pending Stage 4 schema change
  POST /api/reject    -> reject pending Stage 4 schema change
  WS   /ws/events     -> real-time event stream (JSON per message)

WebSocket event schema
----------------------
  {"type": "stage_start" | "stage_done" | "stage_failed" | "approval_required"
           | "heal_complete" | "confidence" | "timeline",
   "payload": { ... }}

The server broadcasts to all connected WebSocket clients so multiple
browser tabs stay in sync automatically.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from agent.mock_orchestrator import MockOrchestrator

app = FastAPI(title="SENTINEL · SRE Control Cockpit")

# Allow the UI to be served from any origin (GitHub Pages, localhost, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_driver = MockOrchestrator()

# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    """Tracks all live WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, event: Dict[str, Any]) -> None:
        """Send a JSON event to every connected client. Dead sockets are pruned."""
        dead: Set[WebSocket] = set()
        payload = json.dumps(event)
        async with self._lock:
            clients = list(self._connections)
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                self._connections -= dead


manager = ConnectionManager()

# Attach broadcaster to the orchestrator so it fires real events
_driver.set_event_callback(
    lambda event: asyncio.get_event_loop().call_soon_threadsafe(
        asyncio.ensure_future, manager.broadcast(event)
    )
)


# ── UI serving ────────────────────────────────────────────────────────────────
_UI_PATH = os.path.join(os.path.dirname(__file__), "..", "ui", "index.html")


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(_UI_PATH)


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status() -> JSONResponse:
    return JSONResponse(_driver.status())


@app.get("/api/memory")
async def get_memory() -> JSONResponse:
    """Return all past incident records for the right-panel memory view."""
    from agent.memory import IncidentMemory
    return JSONResponse(IncidentMemory().to_list())


@app.post("/api/run")
async def post_run() -> Dict[str, Any]:
    run_id = _driver.trigger()
    await manager.broadcast({"type": "heal_started", "payload": {"run_id": run_id}})
    return {"ok": True, "run_id": run_id}


@app.post("/api/approve")
async def post_approve() -> Dict[str, Any]:
    _driver.approve()
    await manager.broadcast({"type": "stage4_approved", "payload": {}})
    return {"ok": True}


@app.post("/api/reject")
async def post_reject() -> Dict[str, Any]:
    _driver.reject()
    await manager.broadcast({"type": "stage4_rejected", "payload": {}})
    return {"ok": True}


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket) -> None:
    await manager.connect(ws)
    # Send current status immediately on connect so the UI syncs on reload
    await ws.send_text(json.dumps({"type": "status_sync", "payload": _driver.status()}))
    try:
        while True:
            # Keep connection alive; the server pushes, client mostly listens
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping", "payload": {}}))
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)


# ── Entry point ───────────────────────────────────────────────────────────────

def run(host: str = "0.0.0.0", port: int = 8080) -> None:
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
