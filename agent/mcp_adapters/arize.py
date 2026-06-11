"""
Arize Phoenix MCP Adapter — UPGRADED
-------------------------------------
Exposes the full Phoenix MCP surface to SENTINEL:
  • list_recent_traces()    — see own last N decisions
  • search_spans()          — drill into a past decision
  • run_evaluator()         — LLM-as-a-Judge on a trace
  • get_drift_signals()     — detect behavioral drift
  • save_to_dataset()       — promote good traces to training sets
  • self_improve_prompt()   — generate an improved system prompt
                              from the agent's own eval history

Falls back to a rich local mock when PHOENIX_API_KEY is not set,
so the demo runs fully offline with realistic synthetic data.
"""
from __future__ import annotations

import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional

from agent.jsonrpc.client import JSONRPCClient


class ArizeAdapter:
    def __init__(self, endpoint: Optional[str] = None, **client_kwargs):
        self._live = bool(os.getenv("PHOENIX_API_KEY"))
        if self._live and endpoint:
            self.client = JSONRPCClient(endpoint, **client_kwargs)
        else:
            self.client = None

    # ── core trace ingest ──────────────────────────────────────────────────
    def ingest_trace_and_evaluate(self, trace: dict) -> Dict[str, Any]:
        if self._live and self.client:
            params = {"action": "ingest_and_score", "payload": {"trace": trace}}
            return self.client.call_method("mcp.exec", params)
        return self._mock_ingest(trace)

    def get_compliance_report(self, run_id: str) -> Dict[str, Any]:
        if self._live and self.client:
            params = {"action": "get_report", "payload": {"run_id": run_id}}
            return self.client.call_method("mcp.exec", params)
        return self._mock_report(run_id)

    # ── Phoenix MCP self-introspection tools ───────────────────────────────
    def list_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the agent's N most-recent Phoenix spans."""
        if self._live and self.client:
            params = {"action": "list_recent_traces", "payload": {"limit": limit}}
            return self.client.call_method("mcp.exec", params)
        return self._mock_traces(limit)

    def search_spans(self, trace_id: str, *, filter_tag: Optional[str] = None) -> Dict[str, Any]:
        """Drill into a specific past decision by trace_id."""
        if self._live and self.client:
            params = {"action": "search_spans", "payload": {"trace_id": trace_id, "filter_tag": filter_tag}}
            return self.client.call_method("mcp.exec", params)
        return self._mock_span(trace_id)

    def run_evaluator(
        self,
        trace_id: str,
        *,
        eval_template: str = "correctness",
        reference_dataset: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run an LLM-as-a-Judge evaluation on a past trace."""
        if self._live and self.client:
            params = {
                "action": "run_evaluator",
                "payload": {"trace_id": trace_id, "template": eval_template, "reference_dataset": reference_dataset},
            }
            return self.client.call_method("mcp.exec", params)
        return self._mock_eval(trace_id, eval_template)

    def get_drift_signals(self, service_id: str, *, window_hours: int = 24) -> Dict[str, Any]:
        """Get behavioral drift signals for a service over a time window."""
        if self._live and self.client:
            params = {"action": "get_drift_signals", "payload": {"service_id": service_id, "window_hours": window_hours}}
            return self.client.call_method("mcp.exec", params)
        return self._mock_drift(service_id)

    def save_to_dataset(self, trace_id: str, dataset_name: str = "sentinel_golden_traces") -> Dict[str, Any]:
        """Promote a high-quality trace to a Phoenix dataset."""
        if self._live and self.client:
            params = {"action": "save_to_dataset", "payload": {"trace_id": trace_id, "dataset": dataset_name}}
            return self.client.call_method("mcp.exec", params)
        return {"saved": True, "dataset": dataset_name, "trace_id": trace_id}

    def self_improve_prompt(self, current_prompt: str, *, eval_threshold: float = 0.75) -> Dict[str, Any]:
        """
        Introspect recent evals. If average score < threshold, return a
        suggested improved system prompt grounded in failing trace patterns.
        This is the crown jewel of the Arize self-improvement loop.
        """
        recent = self.list_recent_traces(limit=20)
        scores = [t.get("eval_score", 0.9) for t in recent if "eval_score" in t]
        avg = sum(scores) / len(scores) if scores else 0.9

        if avg >= eval_threshold:
            return {
                "improvement_needed": False,
                "avg_eval_score": round(avg, 4),
                "message": "Agent performance above threshold — no prompt update needed.",
            }

        failing_patterns = [
            t.get("error_tag", "unknown")
            for t in recent
            if t.get("eval_score", 1.0) < eval_threshold
        ]
        unique_patterns = list(set(failing_patterns))

        improved_prompt = (
            current_prompt
            + "\n\n# Auto-improvement addendum (generated by SENTINEL self-eval loop)\n"
            + "Focus extra attention on: "
            + ", ".join(unique_patterns)
            + ".\nAlways query search_spans() before patching any collection touched by these errors."
        )

        return {
            "improvement_needed": True,
            "avg_eval_score": round(avg, 4),
            "failing_patterns": unique_patterns,
            "improved_prompt": improved_prompt,
        }

    # ── mock implementations (offline demo) ───────────────────────────────
    def _mock_ingest(self, trace: dict) -> dict:
        return {"run_id": str(uuid.uuid4())[:8], "ingested": True, "spans_captured": len(trace.get("events", []))}

    def _mock_report(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "compliance_score": round(random.uniform(0.88, 0.99), 4),
            "drift_score": round(random.uniform(0.01, 0.15), 4),
            "eval_grade": "A",
            "recommendations": ["Trace saved to sentinel_golden_traces dataset.", "No behavioral drift detected in last 24h."],
        }

    def _mock_traces(self, limit: int) -> List[dict]:
        return [
            {
                "trace_id": str(uuid.uuid4())[:8],
                "ts": time.time() - i * 3600,
                "stage": random.choice(["stage1","stage2","stage3","stage4","stage5","stage6"]),
                "outcome": random.choice(["SUCCESS","SUCCESS","SUCCESS","PARTIAL"]),
                "eval_score": round(random.uniform(0.78, 0.99), 4),
                "error_tag": random.choice(["BSONType","schema_drift","null_field","none"]),
                "latency_ms": random.randint(120, 800),
            }
            for i in range(min(limit, 8))
        ]

    def _mock_span(self, trace_id: str) -> dict:
        return {
            "trace_id": trace_id,
            "spans": [
                {"name": "inspect_collection", "latency_ms": 142, "status": "ok"},
                {"name": "validate_schema",     "latency_ms": 89,  "status": "ok"},
                {"name": "apply_patch",         "latency_ms": 310, "status": "ok"},
            ],
            "root_cause": "BSONType mismatch on field 'amount' (expected double, got string)",
            "resolution": "collMod applied with validator_action=error",
        }

    def _mock_eval(self, trace_id: str, template: str) -> dict:
        score = round(random.uniform(0.82, 0.98), 4)
        return {
            "trace_id": trace_id,
            "template": template,
            "score": score,
            "grade": "A" if score >= 0.9 else "B",
            "feedback": "Agent correctly identified the BSON type mismatch and applied the minimal-invasive collMod without data loss.",
        }

    def _mock_drift(self, service_id: str) -> dict:
        drift = round(random.uniform(0.02, 0.12), 4)
        return {
            "service_id": service_id,
            "drift_score": drift,
            "drift_level": "LOW" if drift < 0.1 else "MEDIUM",
            "signals": [
                {"metric": "schema_violation_rate", "change": "+0.03%", "window": "24h"},
                {"metric": "patch_latency_p99",     "change": "-12ms",  "window": "24h"},
            ],
            "recommendation": "No action needed. Continue monitoring.",
        }
