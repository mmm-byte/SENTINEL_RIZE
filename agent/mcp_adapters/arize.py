"""
Arize Phoenix MCP Adapter — FULL PRODUCTION BUILD
--------------------------------------------------
Exposes the full Phoenix MCP surface to SENTINEL:

  Core
  ----
  • ingest_trace_and_evaluate()   — ingest + score a trace
  • get_compliance_report()       — per-run compliance report

  Self-introspection (Phoenix MCP tools)
  --------------------------------------
  • list_recent_traces()          — agent's last N decisions
  • search_spans()                — drill into a past decision
  • run_evaluator()               — LLM-as-a-Judge on a trace
  • get_eval_dimensions()         — 4-axis eval breakdown
  • get_drift_signals()           — behavioral drift per service
  • get_drift_sparkline()         — 20-point drift history array
  • save_to_dataset()             — promote good traces to sets
  • self_improve_prompt()         — generate improved system prompt

  Comparison & classification
  ---------------------------
  • get_trace_comparison()        — current run vs best golden run
  • classify_incident_severity()  — LOW / MEDIUM / CRITICAL at ingest

Falls back to rich local mocks when PHOENIX_API_KEY is not set,
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
            return self.client.call_method("mcp.exec", {"action": "ingest_and_score", "payload": {"trace": trace}})
        return self._mock_ingest(trace)

    def get_compliance_report(self, run_id: str) -> Dict[str, Any]:
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {"action": "get_report", "payload": {"run_id": run_id}})
        return self._mock_report(run_id)

    # ── Phoenix MCP self-introspection tools ───────────────────────────────

    def list_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the agent's N most-recent Phoenix spans."""
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {"action": "list_recent_traces", "payload": {"limit": limit}})
        return self._mock_traces(limit)

    def search_spans(self, trace_id: str, *, filter_tag: Optional[str] = None) -> Dict[str, Any]:
        """Drill into a specific past decision by trace_id."""
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {"action": "search_spans", "payload": {"trace_id": trace_id, "filter_tag": filter_tag}})
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
            return self.client.call_method("mcp.exec", {
                "action": "run_evaluator",
                "payload": {"trace_id": trace_id, "template": eval_template, "reference_dataset": reference_dataset},
            })
        return self._mock_eval(trace_id, eval_template)

    def get_eval_dimensions(self, trace_id: str) -> Dict[str, Any]:
        """
        Return a 4-axis LLM-as-a-Judge breakdown:
          correctness, groundedness, relevance, toxicity.
        Arize Phoenix evaluators natively support these dimensions.
        """
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {"action": "get_eval_dimensions", "payload": {"trace_id": trace_id}})
        return self._mock_eval_dimensions(trace_id)

    def get_drift_signals(self, service_id: str, *, window_hours: int = 24) -> Dict[str, Any]:
        """Get behavioral drift signals for a service over a time window."""
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {"action": "get_drift_signals", "payload": {"service_id": service_id, "window_hours": window_hours}})
        return self._mock_drift(service_id)

    def get_drift_sparkline(self, service_id: str, *, points: int = 20) -> List[float]:
        """
        Return a list of `points` drift-score floats (oldest → newest).
        Used to render the per-stage sparkline in the SRE cockpit.
        """
        if self._live and self.client:
            result = self.client.call_method("mcp.exec", {"action": "get_drift_sparkline", "payload": {"service_id": service_id, "points": points}})
            return result.get("values", [])
        return self._mock_sparkline(points)

    def save_to_dataset(self, trace_id: str, dataset_name: str = "sentinel_golden_traces") -> Dict[str, Any]:
        """Promote a high-quality trace to a Phoenix dataset."""
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {"action": "save_to_dataset", "payload": {"trace_id": trace_id, "dataset": dataset_name}})
        return {"saved": True, "dataset": dataset_name, "trace_id": trace_id}

    def self_improve_prompt(self, current_prompt: str, *, eval_threshold: float = 0.75) -> Dict[str, Any]:
        """
        Introspect recent evals. If average score < threshold, return a
        suggested improved system prompt grounded in failing trace patterns.
        This is the crown-jewel of the Arize self-improvement loop.
        """
        recent = self.list_recent_traces(limit=20)
        scores = [t.get("eval_score", 0.9) for t in recent if "eval_score" in t]
        avg = sum(scores) / len(scores) if scores else 0.9

        if avg >= eval_threshold:
            return {
                "improvement_needed": False,
                "avg_eval_score": round(avg, 4),
                "message": "Agent performance above threshold — no prompt update needed.",
                "before": current_prompt,
                "after": current_prompt,
                "diff": [],
            }

        failing_patterns = list({
            t.get("error_tag", "unknown")
            for t in recent
            if t.get("eval_score", 1.0) < eval_threshold
        })

        addendum = (
            "\n\n# Auto-improvement addendum (SENTINEL self-eval loop)\n"
            "Focus extra attention on: " + ", ".join(failing_patterns) + ".\n"
            "Always call search_spans() before patching any collection touched by these errors."
        )
        improved_prompt = current_prompt + addendum

        return {
            "improvement_needed": True,
            "avg_eval_score": round(avg, 4),
            "failing_patterns": failing_patterns,
            "before": current_prompt,
            "after": improved_prompt,
            "diff": [
                {"type": "added", "line": line}
                for line in addendum.strip().splitlines()
                if line.strip()
            ],
        }

    # ── comparison & classification ────────────────────────────────────────

    def get_trace_comparison(self, current_trace_id: str) -> Dict[str, Any]:
        """
        Compare the current run against the best golden trace.
        Returns side-by-side metrics: latency, confidence, drift, eval score.
        """
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {
                "action": "get_trace_comparison",
                "payload": {"trace_id": current_trace_id, "dataset": "sentinel_golden_traces"},
            })
        return self._mock_trace_comparison(current_trace_id)

    def classify_incident_severity(self, error_signature: str, drift_score: float, affected_records: int) -> Dict[str, Any]:
        """
        Fast 3-class incident severity classifier (LOW / MEDIUM / CRITICAL).
        Runs at alert ingest — before Stage 1 — to set operator expectations.
        """
        if self._live and self.client:
            return self.client.call_method("mcp.exec", {
                "action": "classify_severity",
                "payload": {"error": error_signature, "drift": drift_score, "records": affected_records},
            })
        return self._mock_classify(error_signature, drift_score, affected_records)

    # ── mock implementations (offline demo) ───────────────────────────────

    def _mock_ingest(self, trace: dict) -> dict:
        return {"run_id": str(uuid.uuid4())[:8], "ingested": True, "spans_captured": len(trace.get("events", []))}

    def _mock_report(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "compliance_score": round(random.uniform(0.88, 0.99), 4),
            "drift_score": round(random.uniform(0.01, 0.15), 4),
            "eval_grade": "A",
            "recommendations": [
                "Trace saved to sentinel_golden_traces dataset.",
                "No behavioral drift detected in last 24h.",
            ],
        }

    def _mock_traces(self, limit: int) -> List[dict]:
        stages = ["stage1_ingest", "stage2_logs", "stage3_git_remediation",
                  "stage4_db_stabilize", "stage5_downstream_align", "stage6_cognitive_assess"]
        return [
            {
                "trace_id": str(uuid.uuid4())[:8],
                "ts": round(time.time() - i * 3600, 0),
                "stage": stages[i % len(stages)],
                "outcome": random.choice(["SUCCESS", "SUCCESS", "SUCCESS", "PARTIAL"]),
                "eval_score": round(random.uniform(0.78, 0.99), 4),
                "error_tag": random.choice(["BSONType", "schema_drift", "null_field", "none"]),
                "latency_ms": random.randint(120, 800),
                "service": random.choice(["payments-svc", "orders-svc", "billing-svc"]),
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
            "feedback": "Agent correctly identified the BSON type mismatch and applied minimal-invasive collMod without data loss.",
        }

    def _mock_eval_dimensions(self, trace_id: str) -> dict:
        correctness   = round(random.uniform(0.88, 0.99), 4)
        groundedness  = round(random.uniform(0.85, 0.98), 4)
        relevance     = round(random.uniform(0.90, 0.99), 4)
        toxicity      = round(random.uniform(0.00, 0.02), 4)
        overall       = round((correctness + groundedness + relevance) / 3, 4)
        return {
            "trace_id": trace_id,
            "dimensions": {
                "correctness":  correctness,
                "groundedness": groundedness,
                "relevance":    relevance,
                "toxicity":     toxicity,
            },
            "overall": overall,
            "grade": "A" if overall >= 0.9 else "B",
            "feedback": "Agent correctly identified the BSON type mismatch and applied minimal-invasive collMod without data loss.",
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

    def _mock_sparkline(self, points: int) -> List[float]:
        """Simulate a realistic drift trend: starts moderate, dips at incident, recovers."""
        base = 0.05
        vals = []
        for i in range(points):
            spike = 0.15 if points // 2 - 2 <= i <= points // 2 else 0.0
            noise = random.uniform(-0.015, 0.015)
            vals.append(round(max(0.0, min(0.5, base + spike + noise)), 4))
        return vals

    def _mock_trace_comparison(self, current_trace_id: str) -> dict:
        return {
            "current": {
                "trace_id": current_trace_id,
                "latency_ms": random.randint(400, 900),
                "confidence": round(random.uniform(0.82, 0.94), 4),
                "drift_score": round(random.uniform(0.05, 0.18), 4),
                "eval_score": round(random.uniform(0.85, 0.97), 4),
            },
            "golden": {
                "trace_id": "a1b2c3d4",
                "latency_ms": 420,
                "confidence": 0.97,
                "drift_score": 0.04,
                "eval_score": 0.97,
                "dataset": "sentinel_golden_traces",
            },
        }

    def _mock_classify(self, error_signature: str, drift_score: float, affected_records: int) -> dict:
        if drift_score > 0.35 or affected_records > 100_000:
            severity, color = "CRITICAL", "#EF4444"
        elif drift_score > 0.15 or affected_records > 10_000:
            severity, color = "MEDIUM", "#FBBF24"
        else:
            severity, color = "LOW", "#10B981"
        return {
            "severity": severity,
            "color": color,
            "drift_score": drift_score,
            "affected_records": affected_records,
            "rationale": f"drift={drift_score:.2f}, records={affected_records:,} → {severity}",
            "auto_heal_eligible": severity != "CRITICAL",
        }
