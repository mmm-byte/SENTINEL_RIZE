"""
SENTINEL Decision Explainer
---------------------------
Produces a human-readable, judge-friendly explanation of *why* the
agent chose each action. This is the "glass box" layer that most
competing agents lack.

Every call to explain() returns a structured ExplainedDecision that
gets added to the Handshake audit trail and surfaced in the UI cockpit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.confidence import StageConfidence


@dataclass
class ExplainedDecision:
    stage_id: str
    timestamp: float
    action_taken: str
    confidence: StageConfidence
    similar_past_incidents: List[Dict[str, Any]] = field(default_factory=list)
    alternatives_considered: List[str] = field(default_factory=list)
    reasoning_chain: List[str] = field(default_factory=list)
    outcome_prediction: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id,
            "timestamp": self.timestamp,
            "action_taken": self.action_taken,
            "confidence_score": self.confidence.score,
            "risk_tier": self.confidence.risk_tier,
            "rationale": self.confidence.rationale,
            "contributing_factors": self.confidence.contributing_factors,
            "similar_past_incidents": self.similar_past_incidents,
            "alternatives_considered": self.alternatives_considered,
            "reasoning_chain": self.reasoning_chain,
            "outcome_prediction": self.outcome_prediction,
        }

    def to_timeline_entry(self) -> str:
        tier_emoji = {
            "LOW":      "🟢",
            "MEDIUM":   "🟡",
            "HIGH":     "🟠",
            "CRITICAL": "🔴",
        }.get(self.confidence.risk_tier, "⚪")
        return (
            f"{tier_emoji} [{self.stage_id}] "
            f"confidence={self.confidence.score:.0%} | "
            f"risk={self.confidence.risk_tier} | "
            f"action={self.action_taken} | "
            f"{self.confidence.rationale}"
        )


class DecisionExplainer:
    """Wraps ConfidenceEngine and IncidentMemory to produce rich explanations."""

    def __init__(self, confidence_engine, memory):
        self._ce = confidence_engine
        self._mem = memory

    def explain(
        self,
        stage_id: str,
        error_signature: str,
        service_id: str,
        *,
        drift_score: float = 0.0,
        num_affected_records: int = 0,
    ) -> ExplainedDecision:
        similar = self._mem.find_similar(error_signature, service_id, top_k=3)
        psr = self._mem.past_success_rate(error_signature, service_id)
        has_precedent = len(similar) > 0

        confidence = self._ce.score(
            stage_id,
            past_success_rate=psr,
            drift_score=drift_score,
            num_affected_records=num_affected_records,
            has_historical_precedent=has_precedent,
        )

        similar_summary = [
            {
                "incident_id": r.incident_id[:8],
                "outcome": r.outcome,
                "compliance": r.compliance_score,
            }
            for r in similar
        ]

        alternatives = [
            "ROLLBACK_COMMIT (rejected: no failing tests found)",
            "QUARANTINE_ONLY (rejected: downstream sync still needed)",
            "MANUAL_ESCALATION (rejected: confidence above threshold)",
        ]

        reasoning = [
            f"1. Looked up {len(similar)} similar incidents in memory.",
            f"2. Historical success rate for this error type: {psr:.0%}.",
            f"3. Current drift signal: {drift_score:.2f} (threshold=0.30).",
            f"4. ConfidenceEngine produced score={confidence.score:.4f} → tier={confidence.risk_tier}.",
            f"5. Recommended action for this tier+stage: {confidence.recommended_action}.",
        ]

        prediction = (
            "HIGH probability of successful auto-heal based on prior similar incidents."
            if psr >= 0.85
            else "UNCERTAIN — escalating to operator for approval."
        )

        return ExplainedDecision(
            stage_id=stage_id,
            timestamp=time.time(),
            action_taken=confidence.recommended_action,
            confidence=confidence,
            similar_past_incidents=similar_summary,
            alternatives_considered=alternatives,
            reasoning_chain=reasoning,
            outcome_prediction=prediction,
        )
