"""
Smoke tests for agent.memory.IncidentMemory
"""
import time
import pytest
from agent.memory import IncidentMemory, IncidentRecord


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton between tests so state doesn't bleed."""
    IncidentMemory._instance = None
    yield
    IncidentMemory._instance = None


@pytest.fixture
def mem():
    return IncidentMemory()


class TestSingleton:
    def test_same_instance(self):
        a = IncidentMemory()
        b = IncidentMemory()
        assert a is b


class TestSeeding:
    def test_seeded_on_init(self, mem):
        assert len(mem.all_records()) >= 3

    def test_seeded_ids_present(self, mem):
        ids = {r.incident_id for r in mem.all_records()}
        assert "a1b2c3d4" in ids
        assert "e5f6a7b8" in ids
        assert "c9d0e1f2" in ids


class TestRecord:
    def test_can_add_record(self, mem):
        before = len(mem.all_records())
        rec = IncidentRecord(
            incident_id="test-001",
            error_signature="NullPointerException",
            service_id="billing-svc",
            timestamp=time.time(),
            stages_completed=["stage1", "stage2"],
            outcome="SUCCESS",
            compliance_score=0.92,
            drift_score=0.03,
            patch_summary="NPE fixed",
            duration_seconds=5.0,
        )
        mem.record(rec)
        assert len(mem.all_records()) == before + 1

    def test_record_overwrites_same_id(self, mem):
        rec1 = IncidentRecord("dup-001", "err", "svc", time.time(), [], "SUCCESS", None, None, None, None)
        rec2 = IncidentRecord("dup-001", "err", "svc", time.time(), [], "FAILED",  None, None, None, None)
        mem.record(rec1)
        mem.record(rec2)
        found = next(r for r in mem.all_records() if r.incident_id == "dup-001")
        assert found.outcome == "FAILED"


class TestFindSimilar:
    def test_finds_by_error_signature(self, mem):
        results = mem.find_similar("BSONType mismatch", "unknown-svc")
        assert len(results) > 0
        assert all(r.error_signature == "BSONType mismatch" for r in results)

    def test_finds_by_service_id(self, mem):
        results = mem.find_similar("unknown-error", "payments-svc")
        assert len(results) > 0

    def test_top_k_respected(self, mem):
        # Add extras
        for i in range(10):
            mem.record(IncidentRecord(f"bulk-{i}", "BSONType mismatch", "payments-svc",
                                     time.time(), [], "SUCCESS", None, None, None, None))
        results = mem.find_similar("BSONType mismatch", "payments-svc", top_k=3)
        assert len(results) <= 3

    def test_sorted_most_recent_first(self, mem):
        mem.record(IncidentRecord("old", "sig-x", "svc-x", time.time() - 1000, [], "SUCCESS", None, None, None, None))
        mem.record(IncidentRecord("new", "sig-x", "svc-x", time.time(),          [], "SUCCESS", None, None, None, None))
        results = mem.find_similar("sig-x", "svc-x")
        assert results[0].incident_id == "new"


class TestSuccessRate:
    def test_all_success_gives_1(self, mem):
        # Seed only success records
        for i in range(3):
            mem.record(IncidentRecord(f"s{i}", "clean-err", "clean-svc",
                                     time.time(), [], "SUCCESS", None, None, None, None))
        rate = mem.past_success_rate("clean-err", "clean-svc")
        assert rate == 1.0

    def test_no_records_gives_1(self, mem):
        rate = mem.past_success_rate("never-seen-error", "ghost-svc")
        assert rate == 1.0

    def test_mixed_outcome_rate(self, mem):
        for i in range(4):
            outcome = "SUCCESS" if i < 3 else "FAILED"
            mem.record(IncidentRecord(f"mix-{i}", "mixed-err", "mix-svc",
                                     time.time(), [], outcome, None, None, None, None))
        rate = mem.past_success_rate("mixed-err", "mix-svc")
        assert rate == pytest.approx(0.75)


class TestStats:
    def test_stats_has_required_keys(self, mem):
        s = mem.stats()
        assert "total" in s
        assert "success_rate" in s
        assert "avg_duration" in s

    def test_total_matches_record_count(self, mem):
        s = mem.stats()
        assert s["total"] == len(mem.all_records())


class TestToList:
    def test_to_list_returns_list_of_dicts(self, mem):
        result = mem.to_list()
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_to_list_contains_incident_id(self, mem):
        result = mem.to_list()
        assert all("incident_id" in r for r in result)
