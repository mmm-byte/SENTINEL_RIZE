# SENTINEL — Hackathon Winning Features

This document explains the **five key upgrades** that differentiate SENTINEL from every other submission in the Arize Phoenix track.

---

## 1. 🎯 Confidence Engine (`agent/confidence.py`)

Most agents blindly execute every remediation step. SENTINEL **gates each stage behind a deterministic confidence score** (0–1) computed from:

- `past_success_rate` — pulled from Phoenix trace history
- `drift_score` — from Arize drift signal API
- `num_affected_records` — inverse-log scale blast-radius penalty
- `has_historical_precedent` — binary flag from IncidentMemory

The score maps to a **risk tier** (LOW / MEDIUM / HIGH / CRITICAL) and a **recommended action** (AUTO_HEAL / REQUEST_APPROVAL / ESCALATE / ABORT). Judges can read the formula directly in source — there is no black box.

```
confidence = 0.45 × success_rate
           + 0.30 × (1 − drift_score)
           + 0.15 × scale_factor(affected_records)
           + 0.10 × has_precedent
```

---

## 2. 🧠 Incident Memory (`agent/memory.py`)

Before every stage, SENTINEL queries a persistent store of past incidents and finds the top-K most similar by error signature and service ID. This feeds:

1. The `past_success_rate` input to the Confidence Engine.
2. The **Similar Past Incidents** panel in the SRE cockpit — so judges see the agent learning from its own history.

The store is JSON-backed offline and Phoenix-dataset-backed live. It seeds realistic demo data automatically so the panel is never empty.

---

## 3. 🔍 Decision Explainer (`agent/explainer.py`)

Every agent action produces an `ExplainedDecision` that records:

- The confidence score and risk tier
- **Alternatives considered and why they were rejected**
- A 5-step **reasoning chain** (readable by judges in Phoenix traces)
- An **outcome prediction** in plain English

This is the glass-box layer. When a judge asks "why did the agent approve this patch?", the answer is a structured object in the Phoenix span — not a log line.

---

## 4. 🔮 Upgraded Arize Adapter (`agent/mcp_adapters/arize.py`)

The original adapter had 2 methods. The upgraded adapter exposes the **full Phoenix MCP surface**:

| Method | Purpose |
|---|---|
| `list_recent_traces()` | See own last N decisions |
| `search_spans()` | Drill into a past decision by trace_id |
| `run_evaluator()` | LLM-as-a-Judge scoring on any trace |
| `get_drift_signals()` | Detect behavioral drift per service |
| `save_to_dataset()` | Promote golden traces to training sets |
| `self_improve_prompt()` | **Generate improved system prompt from eval history** |

All methods fall back to rich local mocks when `PHOENIX_API_KEY` is not set.

---

## 5. 🖥️ Overhauled SRE Cockpit (`ui/index.html`)

Fully rebuilt from static mockup to live interactive dashboard:

- **Per-stage confidence bars** that animate during each stage
- **Live Confidence Panel** — score, risk tier, recommended action, drift signal
- **Agent Reasoning Chain** panel — judges see *why* each decision was made
- **Similar Past Incidents (Memory)** panel — visual proof of learning
- **Phoenix Eval Score** display post-run
- **Phoenix Self-Improve button** — triggers self-improvement loop live
- KPI bar: MTTD, MTTR, Compliance, Confidence, Incidents Healed counter
- Full animated state machine: idle → running → awaiting_approval → success/failed
