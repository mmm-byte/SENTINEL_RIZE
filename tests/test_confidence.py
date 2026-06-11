"""
Smoke tests for agent.confidence.ConfidenceEngine
"""
import pytest
from agent.confidence import ConfidenceEngine, StageConfidence


@pytest.fixture
def engine():
    return ConfidenceEngine()


class TestScoreRange:
    def test_score_is_between_0_and_1(self, engine):
        result = engine.score("stage1", past_success_rate=0.8, drift_score=0.1)
        assert 0.0 <= result.score <= 1.0

    def test_perfect_inputs_give_high_score(self, engine):
        result = engine.score(
            "stage1",
            past_success_rate=1.0,
            drift_score=0.0,
            num_affected_records=0,
            has_historical_precedent=True,
        )
        assert result.score >= 0.85
        assert result.risk_tier == "LOW"

    def test_bad_inputs_give_low_score(self, engine):
        result = engine.score(
            "stage1",
            past_success_rate=0.2,
            drift_score=0.9,
            num_affected_records=500_000,
            has_historical_precedent=False,
        )
        assert result.score < 0.65

    def test_manual_override_is_respected(self, engine):
        result = engine.score("stage1", manual_override=0.72)
        assert result.score == 0.72

    def test_manual_override_clamps_above_1(self, engine):
        result = engine.score("stage1", manual_override=1.5)
        assert result.score == 1.0

    def test_manual_override_clamps_below_0(self, engine):
        result = engine.score("stage1", manual_override=-0.5)
        assert result.score == 0.0


class TestRiskTiers:
    def test_low_tier(self, engine):
        r = engine.score("s", manual_override=0.90)
        assert r.risk_tier == "LOW"

    def test_medium_tier(self, engine):
        r = engine.score("s", manual_override=0.75)
        assert r.risk_tier == "MEDIUM"

    def test_high_tier(self, engine):
        r = engine.score("s", manual_override=0.50)
        assert r.risk_tier == "HIGH"

    def test_critical_tier(self, engine):
        r = engine.score("s", manual_override=0.20)
        assert r.risk_tier == "CRITICAL"


class TestRecommendedAction:
    def test_low_risk_is_auto_heal(self, engine):
        r = engine.score("stage1", manual_override=0.90)
        assert r.recommended_action == "AUTO_HEAL"

    def test_db_stage_medium_requests_approval(self, engine):
        r = engine.score("stage4_db_stabilize", manual_override=0.75)
        assert r.recommended_action == "REQUEST_APPROVAL"

    def test_non_db_medium_is_auto_heal(self, engine):
        r = engine.score("stage2_logs", manual_override=0.75)
        assert r.recommended_action == "AUTO_HEAL"

    def test_critical_escalates(self, engine):
        r = engine.score("stage1", manual_override=0.20)
        assert r.recommended_action == "ESCALATE"


class TestContributingFactors:
    def test_warning_for_low_success_rate(self, engine):
        r = engine.score("s", past_success_rate=0.5)
        assert any("success rate" in f.lower() for f in r.contributing_factors)

    def test_warning_for_high_drift(self, engine):
        r = engine.score("s", drift_score=0.8)
        assert any("drift" in f.lower() for f in r.contributing_factors)

    def test_warning_for_large_blast_radius(self, engine):
        r = engine.score("s", num_affected_records=50_000)
        assert any("blast radius" in f.lower() or "records" in f.lower() for f in r.contributing_factors)

    def test_green_factors_when_all_ok(self, engine):
        r = engine.score(
            "s",
            past_success_rate=1.0,
            drift_score=0.0,
            num_affected_records=0,
            has_historical_precedent=True,
        )
        assert any("green" in f.lower() for f in r.contributing_factors)


class TestReturnType:
    def test_returns_stage_confidence(self, engine):
        r = engine.score("stage1")
        assert isinstance(r, StageConfidence)

    def test_stage_id_preserved(self, engine):
        r = engine.score("my_stage")
        assert r.stage_id == "my_stage"

    def test_rationale_is_non_empty(self, engine):
        r = engine.score("s", past_success_rate=0.9, drift_score=0.05)
        assert len(r.rationale) > 0
