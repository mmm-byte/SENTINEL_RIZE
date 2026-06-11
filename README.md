# 🛡️ SENTINEL · Arize Phoenix Track

> **An autonomous AI agent that observes its own behavior with Arize Phoenix tracing, scores it with LLM-as-a-Judge evals, and uses its own traces as runtime context to self-improve — running on Google ADK + Gemini.**

[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-ADK%20%2B%20Gemini-4285F4?logo=googlecloud)](https://cloud.google.com/)
[![Arize](https://img.shields.io/badge/Arize-Phoenix%20%2B%20MCP-7B61FF?logo=arize)](https://phoenix.arize.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Google Cloud Rapid Agent Hackathon 2026 · Arize Partner Track**

---

## 🎯 The Problem

AI agents in production are black boxes. When an agent makes a bad decision — a hallucinated schema patch, a runaway loop, a missed quarantine — there is no built-in feedback loop that lets the agent see *what it just did* and *why it failed*. Teams rely on offline log scraping and postmortems.

**SENTINEL turns Arize Phoenix into the agent's runtime self-introspection layer.** Every tool call, every LLM step, every decision becomes a trace the agent can query *while it is still running*.

---

## 🤖 What SENTINEL Does (Arize-flavored)

SENTINEL wraps its 5-step remediation pipeline (Inspect → Validate → Patch → Quarantine → Report) with **OpenInference auto-instrumentation** and exposes the **Phoenix MCP server** so the Gemini agent can query its own operational data as tools:

```
  ALERT RECEIVED
       │
       ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  ADK + Gemini LlmAgent (instrumented with OpenInference)    │
 │                                                             │
 │   Every LLM call → span (auto-captured to Phoenix)          │
 │   Every tool call → span with inputs, outputs, latency      │
 │   Every decision → span with rationale + alternative choices │
 └────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  Phoenix MCP Server (npx @arizeai/phoenix-mcp)              │
 │                                                             │
 │  Tools exposed to the agent at runtime:                     │
 │   • list_recent_traces()       — see own last 10 decisions  │
 │   • search_spans(trace_id)     — drill into a past decision │
 │   • run_evaluator(...)         — LLM-as-a-Judge on a trace  │
 │   • get_drift_signals(...)     — detect behavioral drift    │
 │   • save_to_dataset(...)       — promote good traces to sets│
 └────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
       Agent uses its OWN past traces to choose the
       safest next action. This is the self-improvement loop.
```

### The self-improvement loop judges will see

1. Agent receives a schema-drift alert
2. Agent inspects the collection
3. **Before patching**, agent calls `search_spans(trace_id)` to find similar past incidents and how they were resolved
4. Agent calls `run_evaluator(...)` to score its *current* reasoning against historical quality
5. Agent picks a patch strategy informed by what worked before
6. After the action, the new trace is evaluated and saved to a Phoenix dataset for the next incident

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│              SENTINEL · ARIZE AGENT                      │
│        google.adk.agents.LlmAgent (Gemini 2.0 Flash)      │
│        Auto-instrumented with OpenInference               │
└────────────────┬────────────────────────────┬────────────┘
                 │                            │
        traces flow to                  queries flow from
                 │                            │
                 ▼                            ▼
        ┌────────────────┐         ┌────────────────────┐
        │  Phoenix Cloud │◀────────│  Phoenix MCP Server│
        │  (OTLP/HTTPS)  │         │  npx @arizeai/      │
        │                │         │       phoenix-mcp  │
        │  • Spans       │         │  • list_recent_... │
        │  • Evals       │         │  • search_spans    │
        │  • Datasets    │         │  • run_evaluator   │
        └────────────────┘         └─────────┬──────────┘
                                             │
                                             ▼
                                  SENTINEL self-improvement
                                  loop (no offline re-training)
```

The full SENTINEL monorepo is in this repo. The `core/`, `agent/`, `demo/`, and `ui/` folders contain the implemented engine; the Arize-specific integration points are:

- [`agent/mcp_adapters/arize.py`](agent/mcp_adapters/arize.py) — Phoenix MCP client
- [`tracks/arize/README.md`](tracks/arize/README.md) — track notes

---

## ⚡ Quick Start

### Prerequisites

- Python 3.11+
- A free [Phoenix Cloud](https://phoenix.arize.com/) account and API key
- A Google Cloud project with Gemini API enabled
- Node.js 18+ (for the Phoenix MCP server via `npx`)

### 1 — Clone & Install

```bash
git clone https://github.com/mmm-byte/SENTINEL_RIZE.git
cd SENTINEL_RIZE
pip install -r requirements.txt
npm install -g @arizeai/phoenix-mcp
pip install openinference-instrumentation-google-adk
```

### 2 — Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com
PHOENIX_API_KEY=your-phoenix-api-key
GEMINI_MODEL=gemini-2.0-flash-exp
GOOGLE_API_KEY=your-gemini-api-key
```

### 3 — Configure the Phoenix MCP server

Add to your ADK / Gemini CLI MCP config (`.gemini/settings.json` or ADK config):

```json
{
  "mcpServers": {
    "phoenix": {
      "command": "npx",
      "args": ["-y", "@arizeai/phoenix-mcp"],
      "env": {
        "PHOENIX_COLLECTOR_ENDPOINT": "https://app.phoenix.arize.com",
        "PHOENIX_API_KEY": "<your-key>"
      }
    }
  }
}
```

### 4 — Run SENTINEL with self-introspection

```bash
python -m demo.run_full_demo
# In another terminal:
python -m agent.ui_server
# Open http://127.0.0.1:8080 — the SRE Control Cockpit
# Watch traces land in Phoenix Cloud in real time.
```

---

## 📂 What is in this repo

| Folder | Purpose |
|---|---|
| `agent/` | The core SENTINEL engine (Gemini LlmAgent + tool pipeline) |
| `core/sentinel/` | Schema inspect / validate / patch / quarantine primitives |
| `agent/mcp_adapters/arize.py` | Phoenix MCP client integration |
| `demo/` | End-to-end demo runner with drift injection |
| `ui/cockpit/` | SRE Control Cockpit (the demo dashboard) |
| `tracks/arize/` | Track-specific notes |
| `docs/` | Full architecture and judge summary |

## 📊 Submission status (honest)

- ✅ ADK + Gemini LlmAgent code-owned runtime
- ✅ OpenInference auto-instrumentation hooks present in `agent/orchestrator.py`
- ✅ Phoenix MCP server config in `.env.example` and `tracks/arize/README.md`
- ⚠️ The Phoenix MCP call patterns are scaffolded in `agent/mcp_adapters/arize.py` — the live self-improvement loop runs against a local mock when no Phoenix key is configured, so the demo is **fully runnable offline** and will upgrade to live Phoenix automatically when the env vars are set.

## 🏆 Track fit

SENTINEL is built on the [Google ADK](https://google.github.io/adk-docs/) (code-owned runtime, satisfies the Arize track requirement) and uses the [OpenInference](https://github.com/Arize-ai/openinference) standard to emit traces to Phoenix. The MCP integration lets the agent query its own operational data at runtime — the core of the self-improvement loop Arize is scoring on.
