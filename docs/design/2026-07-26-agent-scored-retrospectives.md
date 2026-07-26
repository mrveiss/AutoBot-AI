---
tags: [type/architecture, status/proposed, component/backend, component/llc]
date: 2026-07-26
issue: 12619
umbrella: 12617
---

# Agent-Scored Sprint Retrospectives

## Overview

The sprint retrospective summarizes *work product*, not *agent performance over time*. The raw per-agent signal already exists in the LLC but is never aggregated or surfaced. This design adds a **per-agent scorecard** — success rate, throughput, and spend — computed from data the LLC already writes, and shown in the retrospective.

**Scope:** aggregation + presentation. No new data collection.

## Problem

Existing retro surface:
- `llc/models/enums.py` — `SprintStatus.RETROSPECTIVE` stage exists.
- `llc/kb/sprint_summarizer.py` — LLM "Learnings" summary merged into the project KB on sprint close.
- `llc/services/sprint_planning.py` — team-level velocity/burndown only.

Existing but unused per-agent signal:
- `llc/models/heartbeat_run.py` — per-agent run records (`agent_id`, `status`, `started_at`).
- `llc/api/costs.py` `/costs/by-agent-model` — per-agent token spend + cache-hit breakdown.

Result: no way to see which specialist agents are reliable vs. regressing across sprints — the exact input routing and hiring decisions need.

## Goals / Non-Goals

**Goals**
- A per-agent scorecard for a sprint (or company/time window).
- Metrics: success rate, throughput, spend.
- Surface the scorecard in the retrospective summary + a read API.

**Non-Goals**
- New telemetry or run-level data collection (reuse existing rows).
- Cross-sprint trend charts / streaks in v1 (the aggregate is the foundation; trends are a fast-follow once historical scorecards accumulate).
- Frontend dashboard (read API is provided; UI is out of scope here).

## Metrics

Per agent, over the sprint window:

| Metric | Definition | Source |
|--------|-----------|--------|
| Success rate | `DONE runs / total runs` | `heartbeat_run` (`status`) |
| Throughput | completed work items (fallback: successful runs) | `heartbeat_run` + work-item relations |
| Spend | tokens / cost | `/costs/by-agent-model` |

Edge cases: an agent with **zero** runs in the window appears with `runs=0`, `success_rate=None` (not `0.0`, to avoid punishing idle/unassigned agents). Division guards throughout.

## Architecture

```
Sprint close / retro request
            │
            ▼
   AgentScorecardService.build(company_id, sprint_id | window)
            │
            ├─ query heartbeat_run rows for window  ─► per-agent {runs, done, started…}
            ├─ query /costs/by-agent-model           ─► per-agent {tokens, cost}
            ▼
     assemble List[AgentScore]  (success_rate, throughput, spend)
            │
      ┌─────┴──────────────────┐
      ▼                         ▼
 sprint_summarizer            GET /sprints/{id}/agent-scorecard
 (append scorecard section    (read API for retro / future UI)
  to Learnings summary)
```

### Service
New `llc/services/agent_scorecard.py`:
- `build(company_id, *, sprint_id=None, window=None) -> list[AgentScore]`
- Pure aggregation; no writes. Reuses existing query paths rather than re-implementing cost math.

### Retro integration
`sprint_summarizer.py` gains a `_render_agent_scorecard(scores)` section appended alongside the existing "Learnings" summary, so the stored `sprint.kb_summary` includes per-agent performance.

### Read API
`GET /sprints/{id}/agent-scorecard` in `llc/api/sprints.py` returns the `AgentScore` list — consumable by the retro now and a frontend later.

## Files affected

- `autobot-backend/llc/services/agent_scorecard.py` — **new** aggregation service.
- `autobot-backend/llc/kb/sprint_summarizer.py` — append scorecard section to the summary.
- `autobot-backend/llc/api/sprints.py` — read endpoint.
- reuse (read-only): `autobot-backend/llc/models/heartbeat_run.py`, `autobot-backend/llc/api/costs.py`.

## Testing

- Aggregation math: success rate, throughput, spend across mixed run outcomes.
- Zero-run agent yields `success_rate=None`, not a divide error.
- Retro summary includes a per-agent section.
- Read API returns the scorecard for a sprint id.

## Future work (out of v1 scope)

Once per-sprint scorecards persist, add cross-sprint trends and streaks (regressing/improving agents) — a presentation layer over accumulated scorecards, no new collection needed.

## Model Used

Opus 4.8 (1M context)
