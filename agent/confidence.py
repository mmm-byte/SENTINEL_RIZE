"""
SENTINEL Confidence Engine
--------------------------
Produces a per-stage confidence score (0-1) and a risk tier
(LOW / MEDIUM / HIGH / CRITICAL) that the agent uses to decide
whether to auto-heal or escalate to a human operator.

This is the key differentiator: instead of blindly executing every
remediation step, SENTINEL gates each stage behind a confidence
check so judges can see *why* the agent trusts (or doesn't trust)
its own next action.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StageConfidence:
    stage_id: str
    score: float          # 0.0 - 1.0
    risk_tier: str        # LOW | MEDIUM | HIGH | CRITICAL
    rationale: str
    recommended_action: str   # AUTO_HEAL | REQUEST_APPROVAL | ESCALATE | ABORT
    contributing_factors: List[str] = field(default_factory=list)


class ConfidenceEngine:
    """LLM-free, deterministic confidence scorer for the 6 remediation stages."""

    TIER_THRESHOLDS = {
        "LOW":      (0.85, 1.00),
        "MEDIUM":   (0.65, 0.85),
        "HIGH":     (0.40, 0.65),
        "CRITICAL": (0.00, 0.40),
    }

    def score(
        self,
        stage_id: str,
        *,
        past_success_rate: float = 1.0,
        drift_score: float = 0.0,
        num_affected_records: int = 0,
        has_historical_precedent: bool = True,
        manual_override: Optional[float] = None,
    ) -> StageConfidence:
        if manual_override is not None:
            raw = float(max(0.0, min(1.0, manual_override)))
        else:
            w_success  = 0.45 * past_success_rate
            w_drift    = 0.30 * (1.0 - drift_score)
            w_scale    = 0.15 * self._scale_factor(num_affected_records)
            w_history  = 0.10 * (1.0 if has_historical_precedent else 0.0)
            raw = w_success + w_drift + w_scale + w_history

        tier = self._tier(raw)
        action = self._action(tier, stage_id)
        factors = self._factors(
            past_success_rate, drift_score,
            num_affected_records, has_historical_precedent
        )

        return StageConfidence(
            stage_id=stage_id,
            score=round(raw, 4),
            risk_tier=tier,
            rationale=(
                f"success_rate={past_success_rate:.0%}, "
                f"drift={drift_score:.2f}, "
                f"records_affected={num_affected_records}, "
                f"has_precedent={has_historical_precedent}"
            ),
            recommended_action=action,
            contributing_factors=factors,
        )

    @staticmethod
    def _scale_factor(n: int) -> float:
        if n <= 0:
            return 1.0
        return max(0.0, 1.0 - math.log10(n + 1) / 6)

    def _tier(self, score: float) -> str:
        for tier, (lo, hi) in self.TIER_THRESHOLDS.items():
            if lo <= score <= hi:
                return tier
        return "CRITICAL"

    @staticmethod
    def _action(tier: str, stage_id: str) -> str:
        if tier == "LOW":
            return "AUTO_HEAL"
        if tier == "MEDIUM":
            return "REQUEST_APPROVAL" if "db" in stage_id else "AUTO_HEAL"
        if tier == "HIGH":
            return "REQUEST_APPROVAL"
        return "ESCALATE"

    @staticmethod
    def _factors(psr: float, ds: float, nr: int, hp: bool) -> List[str]:
        f = []
        if psr < 0.8:
            f.append(f"⚠ Low historical success rate ({psr:.0%})")
        if ds > 0.3:
            f.append(f"⚠ Elevated drift score ({ds:.2f})")
        if nr > 10_000:
            f.append(f"⚠ Large blast radius ({nr:,} records)")
        if not hp:
            f.append("⚠ No historical precedent for this error signature")
        if not f:
            f.append("✓ All confidence indicators green")
        return f
