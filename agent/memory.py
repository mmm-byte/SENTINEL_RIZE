"""
SENTINEL Incident Memory
------------------------
Persistent in-process (or file-backed) store of past healing runs.
The agent reads this before each stage to:
  1. Find similar past incidents (same error signature / service).
  2. Feed past_success_rate into the ConfidenceEngine.
  3. Avoid repeating patches that previously failed.

In production this plugs directly into Phoenix datasets.
For the hackathon demo it runs fully offline as a JSON file.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class IncidentRecord:
    incident_id: str
    error_signature: str
    service_id: str
    timestamp: float
    stages_completed: List[str]
    outcome: str                    # SUCCESS | PARTIAL | FAILED
    compliance_score: Optional[float]
    drift_score: Optional[float]
    patch_summary: Optional[str]
    duration_seconds: Optional[float]
    tags: List[str] = field(default_factory=list)


class IncidentMemory:
    """Read/write interface for SENTINEL's past incident knowledge."""

    def __init__(self, store_path: str = ".sentinel_memory.json"):
        self._path = Path(store_path)
        self._records: Dict[str, IncidentRecord] = {}
        self._load()
        if not self._records:
            self._seed_demo_data()

    def record(self, rec: IncidentRecord) -> None:
        self._records[rec.incident_id] = rec
        self._persist()

    def record_from_handshake(self, h) -> IncidentRecord:
        outcome = "SUCCESS"
        if any(e.get("status") == "failed" for e in (h.audit_trail or []) if isinstance(e, dict)):
            outcome = "PARTIAL"
        started = h.audit_trail[0].get("ts") if h.audit_trail else time.time()
        finished = h.audit_trail[-1].get("ts") if h.audit_trail else time.time()
        duration = (finished - started) if (started and finished) else None
        rec = IncidentRecord(
            incident_id=h.correlation_id,
            error_signature=h.error_string or "unknown",
            service_id=h.service_id or "unknown",
            timestamp=time.time(),
            stages_completed=[e.get("stage", "") for e in (h.audit_trail or []) if isinstance(e, dict)],
            outcome=outcome,
            compliance_score=h.compliance_score,
            drift_score=h.drift_score,
            patch_summary=h.patch_summary,
            duration_seconds=duration,
        )
        self.record(rec)
        return rec

    def find_similar(self, error_signature: str, service_id: str, top_k: int = 5) -> List[IncidentRecord]:
        hits = [
            r for r in self._records.values()
            if r.error_signature == error_signature or r.service_id == service_id
        ]
        hits.sort(key=lambda r: r.timestamp, reverse=True)
        return hits[:top_k]

    def past_success_rate(self, error_signature: str, service_id: str) -> float:
        similar = self.find_similar(error_signature, service_id, top_k=20)
        if not similar:
            return 1.0
        successes = sum(1 for r in similar if r.outcome == "SUCCESS")
        return successes / len(similar)

    def all_records(self) -> List[IncidentRecord]:
        return list(self._records.values())

    def stats(self) -> dict:
        records = self.all_records()
        if not records:
            return {"total": 0, "success_rate": None, "avg_duration": None}
        total = len(records)
        successes = sum(1 for r in records if r.outcome == "SUCCESS")
        durations = [r.duration_seconds for r in records if r.duration_seconds is not None]
        return {
            "total": total,
            "success_rate": round(successes / total, 4),
            "avg_duration": round(sum(durations) / len(durations), 2) if durations else None,
        }

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                self._records = {k: IncidentRecord(**v) for k, v in raw.items()}
            except Exception:
                self._records = {}

    def _persist(self) -> None:
        try:
            self._path.write_text(
                json.dumps({k: asdict(v) for k, v in self._records.items()}, indent=2)
            )
        except Exception:
            pass

    def _seed_demo_data(self) -> None:
        """Seed realistic demo incidents so the UI memory panel is never empty."""
        seeds = [
            IncidentRecord("a1b2c3d4", "BSONType mismatch", "payments-svc", time.time()-86400,
                           ["stage1","stage2","stage3","stage4","stage5","stage6"],
                           "SUCCESS", 0.97, 0.04, "collMod applied", 9.2),
            IncidentRecord("e5f6a7b8", "BSONType mismatch", "payments-svc", time.time()-172800,
                           ["stage1","stage2","stage3","stage4","stage5","stage6"],
                           "SUCCESS", 0.95, 0.06, "collMod applied", 11.1),
            IncidentRecord("c9d0e1f2", "schema_drift", "orders-svc", time.time()-259200,
                           ["stage1","stage2","stage3","stage4"],
                           "PARTIAL", 0.81, 0.19, "patch staged, pending approval", 14.7),
        ]
        for s in seeds:
            self._records[s.incident_id] = s
        self._persist()
