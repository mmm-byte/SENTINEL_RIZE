"""
SENTINEL SRE Control Cockpit — FastAPI server
=============================================
Endpoints
---------
  GET  /                          -> SRE Control Cockpit HTML
  GET  /api/status                -> live status JSON
  GET  /api/traces                -> Phoenix recent traces (idea #1)
  GET  /api/drift/{service_id}    -> drift signals + sparkline (idea #3)
  GET  /api/explainer/{stage_id}  -> why-did-agent-do-that (idea #2)
  GET  /api/comparison/{run_id}   -> current run vs golden trace (idea #8)
  POST /api/self-improve          -> Phoenix self-improve + diff (idea #4)
  POST /api/run                   -> trigger a healing run
  POST /api/run/refused           -> agent-refused CRITICAL scenario (idea #15)
  POST /api/approve               -> approve pending Stage 4 schema change
  POST /api/reject                -> reject pending Stage 4 schema change
  GET  /api/memory                -> all past incident records
  WS   /ws/events                 -> real-time event stream
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from agent.mock_orchestrator import MockOrchestrator
from agent.mcp_adapters.arize import ArizeAdapter

app = FastAPI(title="SENTINEL · SRE Control Cockpit")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_driver = MockOrchestrator()
_arize  = ArizeAdapter()

# ── Explainer data: chosen action + 2 rejected alternatives per stage ───────
_EXPLAINER: Dict[str, Any] = {
    "stage1_ingest": {
        "stage": "Stage 1 — Dynatrace Topology",
        "chosen": {"action": "AUTO_HEAL", "reason": "Confidence 0.94 (LOW risk). 6/6 similar incidents resolved at this stage."},
        "rejected": [
            {"action": "REQUEST_APPROVAL", "reason": "Unnecessary — topology reads are non-destructive."},
            {"action": "ESCALATE",         "reason": "Drift 0.04 is well below 0.15 escalation threshold."},
        ],
        "formula": "0.45×1.00 + 0.30×0.96 + 0.15×1.00 + 0.10×1.00 = 0.938",
        "trace_id": "a1b2c3d4",
    },
    "stage2_logs": {
        "stage": "Stage 2 — Elastic Log Search",
        "chosen": {"action": "AUTO_HEAL", "reason": "Confidence 0.91. Error signature matched in 4 prior incidents, all resolved."},
        "rejected": [
            {"action": "REQUEST_APPROVAL", "reason": "Log reads have zero write impact."},
            {"action": "ABORT",            "reason": "Error is well-understood with a known fix path."},
        ],
        "formula": "0.45×1.00 + 0.30×0.94 + 0.15×1.00 + 0.10×1.00 = 0.932",
        "trace_id": "b3c4d5e6",
    },
    "stage3_git_remediation": {
        "stage": "Stage 3 — GitLab Blame + MR",
        "chosen": {"action": "AUTO_HEAL", "reason": "Confidence 0.87. Phoenix spans confirm 3 prior fixes with same branch pattern."},
        "rejected": [
            {"action": "REQUEST_APPROVAL", "reason": "MR targets hotfix branch, not main. Low blast radius."},
            {"action": "ESCALATE",         "reason": "git blame was unambiguous — single commit fa83b2cc."},
        ],
        "formula": "0.45×0.95 + 0.30×0.91 + 0.15×1.00 + 0.10×1.00 = 0.853",
        "trace_id": "c5d6e7f8",
    },
    "stage4_db_stabilize": {
        "stage": "Stage 4 — MongoDB Schema Patch",
        "chosen": {"action": "REQUEST_APPROVAL", "reason": "Confidence 0.68. collMod targets 48,312 docs. Phoenix drift=0.18 above 0.15 threshold."},
        "rejected": [
            {"action": "AUTO_HEAL", "reason": "Blocked — blast radius >10K AND drift above threshold simultaneously."},
            {"action": "ABORT",     "reason": "Patch is correct but risky — approval is the minimal safe action."},
        ],
        "formula": "0.45×0.82 + 0.30×0.82 + 0.15×0.42 + 0.10×1.00 = 0.682",
        "trace_id": "d7e8f9a0",
    },
    "stage5_downstream_align": {
        "stage": "Stage 5 — Fivetran Resync",
        "chosen": {"action": "AUTO_HEAL", "reason": "Confidence 0.88. All 5 prior resyncs succeeded. Drift recovered to 0.05."},
        "rejected": [
            {"action": "REQUEST_APPROVAL", "reason": "Schema already approved at Stage 4. No second gate."},
            {"action": "ESCALATE",         "reason": "Resync is idempotent — safe to retry."},
        ],
        "formula": "0.45×1.00 + 0.30×0.95 + 0.15×0.90 + 0.10×1.00 = 0.950",
        "trace_id": "e9f0a1b2",
    },
    "stage6_cognitive_assess": {
        "stage": "Stage 6 — Arize Phoenix Self-Assessment",
        "chosen": {"action": "AUTO_HEAL", "reason": "Confidence 0.96. Eval score 0.96 (A). Trace promoted to sentinel_golden_traces."},
        "rejected": [
            {"action": "REQUEST_APPROVAL", "reason": "Eval above 0.9 — no human review needed."},
            {"action": "ESCALATE",         "reason": "Zero anomalies across all 6 spans."},
        ],
        "formula": "0.45×1.00 + 0.30×0.97 + 0.15×1.00 + 0.10×1.00 = 0.991",
        "trace_id": "f1a2b3c4",
    },
}


# ── WebSocket connection manager ───────────────────────────────────────────
class ConnectionManager:
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
_driver.set_event_callback(
    lambda event: asyncio.get_event_loop().call_soon_threadsafe(
        asyncio.ensure_future, manager.broadcast(event)
    )
)


# ── UI serving ───────────────────────────────────────────────────────────────
_UI_PATH = os.path.join(os.path.dirname(__file__), "..", "ui", "index.html")


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(_UI_PATH)


# ── Core REST ──────────────────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status() -> JSONResponse:
    return JSONResponse(_driver.status())


@app.get("/api/memory")
async def get_memory() -> JSONResponse:
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


# ── Arize-powered endpoints ──────────────────────────────────────────────
@app.get("/api/traces")
async def get_traces(limit: int = 10) -> JSONResponse:
    """Idea #1 — live Phoenix trace viewer."""
    return JSONResponse(_arize.list_recent_traces(limit=limit))


@app.get("/api/drift/{service_id}")
async def get_drift(service_id: str) -> JSONResponse:
    """Idea #3 — drift signals + 20-point sparkline."""
    signals   = _arize.get_drift_signals(service_id)
    sparkline = _arize.get_drift_sparkline(service_id)
    return JSONResponse({**signals, "sparkline": sparkline})


@app.get("/api/explainer/{stage_id}")
async def get_explainer(stage_id: str) -> JSONResponse:
    """Idea #2 — why-did-the-agent-do-that modal data."""
    data = _EXPLAINER.get(stage_id)
    if not data:
        return JSONResponse({"error": "unknown stage"}, status_code=404)
    dims = _arize.get_eval_dimensions(data["trace_id"])
    return JSONResponse({**data, "eval_dimensions": dims})


@app.get("/api/comparison/{run_id}")
async def get_comparison(run_id: str) -> JSONResponse:
    """Idea #8 — current run vs best golden trace."""
    return JSONResponse(_arize.get_trace_comparison(run_id))


@app.post("/api/self-improve")
async def post_self_improve() -> Dict[str, Any]:
    """Idea #4 — Phoenix self-improve with before/after diff."""
    current_prompt = (
        "You are SENTINEL, an autonomous SRE healing agent. "
        "For each incident: inspect topology, search logs, identify root cause, "
        "apply minimal patch, verify downstream, report to Phoenix."
    )
    result = _arize.self_improve_prompt(current_prompt)
    await manager.broadcast({"type": "self_improve", "payload": result})
    return result


@app.post("/api/run/refused")
async def post_refused_run() -> Dict[str, Any]:
    """Idea #15 — agent deliberately escalates a CRITICAL incident."""
    severity = _arize.classify_incident_severity(
        "cascading_null_pointer", drift_score=0.48, affected_records=820_000
    )
    scenario = {
        "incident_id": f"refused-{uuid.uuid4().hex[:6]}",
        "error_signature": "cascading_null_pointer — all services",
        "severity": severity,
        "confidence": 0.18,
        "risk_tier": "CRITICAL",
        "action": "ESCALATE",
        "reason": (
            "SENTINEL refused to auto-heal. Drift=0.48 (threshold 0.15). "
            "820,000 records in blast radius. No historical precedent. "
            "Confidence 0.18 is below the 0.40 ESCALATE floor. "
            "Human intervention required."
        ),
        "factors": [
            "⚠ Drift score 0.48 — highest ever for payments-svc",
            "⚠ 820,000 documents in blast radius",
            "⚠ Zero historical precedent for this error signature",
            "⚠ Past success rate: 0% (0/0 prior attempts)",
        ],
    }
    await manager.broadcast({"type": "agent_refused", "payload": scenario})
    return scenario


# ── WebSocket ──────────────────────────────────────────────────────────────────
@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket) -> None:
    await manager.connect(ws)
    await ws.send_text(json.dumps({"type": "status_sync", "payload": _driver.status()}))
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping", "payload": {}}))
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)


# ── Entry point ─────────────────────────────────────────────────────────────────
def run(host: str = "0.0.0.0", port: int = 8080) -> None:
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
