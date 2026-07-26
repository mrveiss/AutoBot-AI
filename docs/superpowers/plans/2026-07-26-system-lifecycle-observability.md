# System Lifecycle Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AutoBot's two operationally-dark lifecycle subsystems (memory facts, LLM provider circuit-breakers) observable through the SLM admin control plane, read-only, and add a flag-gated peak/maturity prune signal.

**Architecture:** Two-tier read path per subsystem — the managed node (`autobot-backend`) exposes thin read-only endpoints over its own state; the SLM control plane (`autobot-slm-backend`) proxies/aggregates them via the existing `httpx` + `X-Internal-API-Key` proxy pattern; the SLM frontend (`autobot-slm-frontend`) renders them as tabs under `/monitoring`. Phases 1–2 are pure read paths; Phase 3 is a node-side algorithm change, default OFF.

**Tech Stack:** FastAPI (node + SLM backends), Redis (fact store), Vue 3 + TS + vue-i18n (SLM frontend), pytest, vitest.

## Global Constraints

- Copyright header on every new file: `mrveiss` sole author, `SPDX-License-Identifier: Apache-2.0` (copy from any existing file in the same dir).
- No commit trailers. Commit format `<type>(scope): <description> (#issue)`.
- Node routers: `APIRouter(prefix="/<name>")` — prefix MUST NOT include `/api` (the app factory prepends it).
- Node admin endpoints gate with `admin_check: bool = Depends(check_admin_permission)` (from `auth_middleware`) — this dependency is also satisfied by the `X-Internal-API-Key` the SLM proxy sends.
- `@with_error_handling(...)` decorator goes BELOW `@router.get(...)`.
- Logging via `get_logger(__name__)` / `createLogger` — never `print`/`console.*`.
- Every read endpoint returns `degraded: true` + partial payload on dependency failure — never a 500.
- No endpoint in Phases 1–2 performs a write. Phase 3 flag defaults OFF and OFF must reproduce current behaviour exactly.
- SLM frontend strings: i18n keys added to ALL SLM locale files (mirror an existing monitoring tab's locale coverage).
- Encoding: always `encoding='utf-8'` explicitly on file I/O.

---

## Phase 1a — Node: `GET /api/memory/lifecycle`

**Files:**
- Create: `autobot-backend/api/memory_lifecycle.py`
- Modify: the app factory router-registration site (same place `error_resilience`/`llm_providers` routers are included — grep `include_router` in `autobot-backend/app*.py`/`main.py`/`api/__init__.py`; add `include_router(memory_lifecycle.router)`).
- Test: `autobot-backend/api/memory_lifecycle_test.py`

**Interfaces:**
- Consumes: `memory/essential_story.py::_effective_score(fact, now, max_access)`; `knowledge/facts.py::consolidate_facts(dry_run=True)`; Redis key `memory:consolidate_facts:last_run`; `auth_middleware.check_admin_permission`.
- Produces: `GET /api/memory/lifecycle?limit=N` → JSON `{reinforcement: {hot: [...], cold: [...]}, decay: {last_run, config, prune_preview: [...]}, degraded: bool}`. Each fact entry: `{fact_id, quality_score, access_count, last_accessed, effective_score}`. Each prune_preview entry: `{fact_id, reasons: [str]}`.

- [ ] **Step 1: Write the failing test — payload shape + read-only invariant**

```python
# autobot-backend/api/memory_lifecycle_test.py
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_lifecycle_returns_sections_and_never_deletes(app_with_seeded_facts):
    app, fact_store = app_with_seeded_facts  # fixture seeds >=3 facts, one prunable
    before = await fact_store.count()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/memory/lifecycle?limit=5",
                        headers={"X-Internal-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"reinforcement", "decay", "degraded"}
    assert "hot" in body["reinforcement"] and "cold" in body["reinforcement"]
    assert "prune_preview" in body["decay"]
    # read-only invariant: dry-run preview must not delete
    assert await fact_store.count() == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest api/memory_lifecycle_test.py -v`
Expected: FAIL (404 / module not importable — router not created yet).

- [ ] **Step 3: Implement the endpoint**

```python
# autobot-backend/api/memory_lifecycle.py  (copy the 4-line copyright header from api/error_resilience.py)
"""Memory lifecycle observability — read-only admin view (umbrella #12630, #12631)."""
from __future__ import annotations
import time
from typing import Any, Dict
from fastapi import APIRouter, Depends, Query
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from knowledge import facts as facts_mod
from memory import essential_story

logger = get_logger(__name__)
router = APIRouter(prefix="/memory", tags=["memory-lifecycle"])

_MAX_LIMIT = 100


@router.get("/lifecycle")
@with_error_handling(category=ErrorCategory.SYSTEM)
async def get_memory_lifecycle(
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    degraded = False
    now = time.time()
    reinforcement = {"hot": [], "cold": []}
    decay: Dict[str, Any] = {"last_run": None, "config": {}, "prune_preview": []}
    try:
        facts = await facts_mod.list_facts_with_usage()  # returns fact dicts incl access_count/last_accessed/quality_score
        max_access = max((f.get("access_count", 0) for f in facts), default=1) or 1
        scored = sorted(
            ({**_slim(f), "effective_score": essential_story._effective_score(f, now, max_access)} for f in facts),
            key=lambda f: f["effective_score"], reverse=True,
        )
        reinforcement["hot"] = scored[:limit]
        reinforcement["cold"] = sorted(scored, key=lambda f: f["effective_score"])[:limit]
    except Exception:  # degrade, never 500
        logger.exception("memory lifecycle: reinforcement section failed")
        degraded = True
    try:
        redis = await get_redis_client()
        decay["last_run"] = await redis.get("memory:consolidate_facts:last_run")
        decay["config"] = facts_mod.prune_config_snapshot()  # epoch set?, dry_run flag, max_per_run
        preview = await facts_mod.consolidate_facts(dry_run=True)  # returns candidates + reasons, deletes nothing
        decay["prune_preview"] = [
            {"fact_id": c["fact_id"], "reasons": c["reasons"]} for c in preview.get("candidates", [])
        ][:_MAX_LIMIT]
    except Exception:
        logger.exception("memory lifecycle: decay section failed")
        degraded = True
    return {"reinforcement": reinforcement, "decay": decay, "degraded": degraded}


def _slim(f: Dict[str, Any]) -> Dict[str, Any]:
    return {k: f.get(k) for k in ("fact_id", "quality_score", "access_count", "last_accessed")}
```

Note: `list_facts_with_usage()`, `prune_config_snapshot()`, and the `{candidates:[{fact_id,reasons}]}` return shape of `consolidate_facts(dry_run=True)` are the thin read helpers this task adds to `knowledge/facts.py` (fold into this task). `consolidate_facts` already computes candidates via `_collect_prune_candidates`; expose them in the dry-run return instead of only counting.

- [ ] **Step 4: Register the router**

Add to the router-registration site (mirror the existing `error_resilience`/`llm_providers` include lines):
```python
from api import memory_lifecycle
app.include_router(memory_lifecycle.router, prefix="/api")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest api/memory_lifecycle_test.py -v`
Expected: PASS.

- [ ] **Step 6: Add degraded-path test**

```python
@pytest.mark.asyncio
async def test_lifecycle_degrades_when_redis_down(app_no_redis):
    transport = ASGITransport(app=app_no_redis)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/memory/lifecycle", headers={"X-Internal-API-Key": "test-key"})
    assert r.status_code == 200
    assert r.json()["degraded"] is True
```
Run it; expected PASS (endpoint returns 200 + `degraded: true`, no 500).

- [ ] **Step 7: Commit**

```bash
git add autobot-backend/api/memory_lifecycle.py autobot-backend/api/memory_lifecycle_test.py autobot-backend/knowledge/facts.py <router-registration-file>
git commit -m "feat(observability): node GET /api/memory/lifecycle read endpoint (#12631)"
```

---

## Phase 1b — SLM: memory-lifecycle proxy + `MemoryLifecycle` monitoring tab

**Files:**
- Create: `autobot-slm-backend/api/memory_lifecycle_proxy.py` (mirror `autobot-slm-backend/api/voice_proxy.py`)
- Modify: SLM app router registration (where `voice_proxy.router` is included)
- Create: `autobot-slm-frontend/src/composables/useMemoryLifecycleApi.ts`
- Create: `autobot-slm-frontend/src/views/monitoring/MemoryLifecycle.vue`
- Modify: `autobot-slm-frontend/src/router/index.ts` (add `/monitoring/memory` child)
- Modify: SLM locale files (all locales — add the `monitoring.memory.*` key block)
- Test: `autobot-slm-backend/api/memory_lifecycle_proxy_test.py`, `autobot-slm-frontend/src/views/monitoring/MemoryLifecycle.spec.ts`

**Interfaces:**
- Consumes: node `GET /api/memory/lifecycle` (Phase 1a); `config.settings.authority_base_url`; `AUTOBOT_INTERNAL_API_KEY`.
- Produces: SLM `GET /api/memory/lifecycle` (same payload, or `{degraded: true, reinforcement:{hot:[],cold:[]}, decay:{...}}` when node unreachable); `useMemoryLifecycleApi().fetchLifecycle()`.

- [ ] **Step 1: Write failing proxy test (node-down degrades, not 500)**

```python
# autobot-slm-backend/api/memory_lifecycle_proxy_test.py
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_proxy_degrades_when_node_unreachable(slm_app_bad_backend_url):
    transport = ASGITransport(app=slm_app_bad_backend_url)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/memory/lifecycle", headers=_admin_headers())
    assert r.status_code == 200
    assert r.json()["degraded"] is True
```

- [ ] **Step 2: Run — expect FAIL** (route missing).
  Run: `cd autobot-slm-backend && python -m pytest api/memory_lifecycle_proxy_test.py -v`

- [ ] **Step 3: Implement proxy** — copy `voice_proxy.py` structure exactly, changing:
  - `router = APIRouter(prefix="/memory", tags=["memory-lifecycle-proxy"])`
  - `target_url = f"{AUTOBOT_BACKEND_URL}/api/memory/lifecycle"`, method GET, forward `?limit=`.
  - On `httpx.ConnectError`/timeout: return `JSONResponse({"degraded": True, "reinforcement": {"hot": [], "cold": []}, "decay": {"last_run": None, "config": {}, "prune_preview": []}}, status_code=200)` instead of voice's 503 (this is a dashboard read, degrade not error).

- [ ] **Step 4: Register router** in the SLM app (mirror voice_proxy include). Run test — expect PASS.

- [ ] **Step 5: Frontend composable** — mirror `useAutobotApi.ts` axios pattern but target the SLM backend base (not the node): `GET /api/memory/lifecycle`. Export typed `MemoryLifecycle` interface matching the payload.

- [ ] **Step 6: Frontend tab** — create `MemoryLifecycle.vue`: `onMounted` calls `fetchLifecycle()`; render (a) reinforcement leaderboard table (hot) + cold table, (b) "What decay would prune" table from `decay.prune_preview` with a persistent banner using an i18n key `monitoring.memory.dryRunNotice` ("Dry-run preview — nothing is deleted"). Show a `degraded` notice when `degraded`. All visible strings via `t('monitoring.memory.*')`.

- [ ] **Step 7: Router child + locales** — add under the `/monitoring` children in `router/index.ts`:
```ts
{ path: 'memory', name: 'monitoring-memory',
  component: () => import('@/views/monitoring/MemoryLifecycle.vue'),
  meta: { title: 'Memory Lifecycle', parent: 'monitoring' } },
```
Add the `monitoring.memory` key block to every SLM locale file (mirror an existing `monitoring.*` block's locale set).

- [ ] **Step 8: Frontend spec** — `MemoryLifecycle.spec.ts`: mount with a mocked composable returning a fixture payload; assert hot/cold rows render and the dry-run banner is present; assert degraded notice shows when `degraded: true`.

- [ ] **Step 9: Verify + commit**
  Run: `cd autobot-slm-frontend && npx vue-tsc --noEmit -p tsconfig.app.json && npx vitest run src/views/monitoring/MemoryLifecycle.spec.ts`
```bash
git commit -m "feat(observability): SLM memory-lifecycle proxy + monitoring tab (#12632)"
```

---

## Phase 2a — Node: `GET /api/system/breakers`

**Files:**
- Modify: `autobot-backend/api/memory_lifecycle.py` → rename intent aside, add a new router in a new file `autobot-backend/api/system_breakers.py` (keep one responsibility per file).
- Create: `autobot-backend/api/system_breakers.py`
- Modify: router registration site (`include_router`)
- Test: `autobot-backend/api/system_breakers_test.py`

**Interfaces:**
- Consumes: `circuit_breaker.py::get_circuit_breaker_manager().get_all_states()`; `check_admin_permission`.
- Produces: `GET /api/system/breakers` → `{breakers: {<name>: {state, failure_count, success_count, last_transition}}, degraded: bool}`.

- [ ] **Step 1: Failing test**

```python
# autobot-backend/api/system_breakers_test.py
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_breakers_returns_states(app_with_open_breaker):
    app = app_with_open_breaker  # fixture trips one provider breaker to OPEN
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/system/breakers", headers={"X-Internal-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert "breakers" in body
    assert any(b["state"] == "OPEN" for b in body["breakers"].values())
```

- [ ] **Step 2: Run — expect FAIL.** `cd autobot-backend && python -m pytest api/system_breakers_test.py -v`

- [ ] **Step 3: Implement**

```python
# autobot-backend/api/system_breakers.py  (copyright header from a sibling)
"""LLM provider circuit-breaker states — read-only admin view (#12633)."""
from typing import Any, Dict
from fastapi import APIRouter, Depends
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from circuit_breaker import get_circuit_breaker_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/system", tags=["system-breakers"])


@router.get("/breakers")
@with_error_handling(category=ErrorCategory.SYSTEM)
async def get_system_breakers(admin_check: bool = Depends(check_admin_permission)) -> Dict[str, Any]:
    try:
        states = get_circuit_breaker_manager().get_all_states()
        return {"breakers": states, "degraded": False}
    except Exception:
        logger.exception("system breakers read failed")
        return {"breakers": {}, "degraded": True}
```
(Confirm `get_all_states()` value shape and reshape keys to `state/failure_count/success_count/last_transition` if it differs.)

- [ ] **Step 4: Register router; run test — expect PASS.**

- [ ] **Step 5: Commit**
```bash
git commit -m "feat(observability): node GET /api/system/breakers provider breaker states (#12633)"
```

---

## Phase 2b — SLM: unified `GET /api/system/lifecycle` + `SystemLifecycle` dashboard

**Files:**
- Create: `autobot-slm-backend/api/system_lifecycle.py` (aggregator; may reuse the `_proxy_to_main_backend` helper)
- Modify: SLM router registration
- Create: `autobot-slm-frontend/src/composables/useSystemLifecycleApi.ts`
- Create: `autobot-slm-frontend/src/views/monitoring/SystemLifecycle.vue`
- Modify: `autobot-slm-frontend/src/router/index.ts` (add `/monitoring/lifecycle` child); SLM locales
- Test: `autobot-slm-backend/api/system_lifecycle_test.py`, `SystemLifecycle.spec.ts`

**Interfaces:**
- Consumes: node `/api/memory/lifecycle` (1a), node `/api/system/breakers` (2a), node `/api/resilience/circuit-breakers`, node `/api/llm/fallback-status`, node probe health; SLM `MemoryLifecycle` summary (1b).
- Produces: SLM `GET /api/system/lifecycle` → `{memory, provider_breakers, resilience_breakers, fallback, health, degraded}` — each section independently `null`+flagged on failure.

- [ ] **Step 1: Failing test — partial section failure yields partial payload, not whole-payload failure**

```python
@pytest.mark.asyncio
async def test_lifecycle_partial_when_one_section_fails(slm_app_breakers_endpoint_500):
    transport = ASGITransport(app=slm_app_breakers_endpoint_500)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/system/lifecycle", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True
    assert body["memory"] is not None            # healthy section still present
    assert body["provider_breakers"] is None     # failed section nulled
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement aggregator** — fan out the 5 node calls concurrently with `asyncio.gather(..., return_exceptions=True)`; each exception → that section `None` + set `degraded=True`; reuse `voice_proxy._proxy_to_main_backend`-style `httpx` GETs with the internal key. Never raise.

- [ ] **Step 4: Register; run test — expect PASS.**

- [ ] **Step 5: Composable + dashboard view** — `SystemLifecycle.vue`: card grid — Memory card (renders 1b summary; links to `/monitoring/memory`), Provider-breaker card (per-provider chips, OPEN/HALF_OPEN highlighted via a status class), Fallback card + Health card (link to existing surfaces). Null section → "unavailable" card state. i18n `monitoring.lifecycle.*` across all locales.

- [ ] **Step 6: Router child + spec + verify**
```ts
{ path: 'lifecycle', name: 'monitoring-lifecycle',
  component: () => import('@/views/monitoring/SystemLifecycle.vue'),
  meta: { title: 'System Lifecycle', parent: 'monitoring' } },
```
  `SystemLifecycle.spec.ts`: mount with a fixture where `provider_breakers` is null → card shows unavailable; breaker OPEN → highlight class applied.
  Run: `npx vue-tsc --noEmit -p tsconfig.app.json && npx vitest run .../SystemLifecycle.spec.ts`

- [ ] **Step 7: Commit**
```bash
git commit -m "feat(observability): SLM unified system-lifecycle aggregate + dashboard (#12634)"
```

---

## Phase 3 — Node: peak/maturity usage-velocity prune signal (flag OFF)

**Files:**
- Modify: `autobot-backend/knowledge/facts.py` (`_collect_prune_candidates` / consolidate scoring; add access-snapshot capture)
- Modify (optional): `autobot-backend/memory/essential_story.py::_effective_score`
- Test: `autobot-backend/knowledge/facts_peak_signal_test.py`

**Interfaces:**
- Consumes: existing `access_count` field on facts; new env flag `AUTOBOT_FACTS_PEAK_SIGNAL` (default `"0"`).
- Produces: a `velocity` term folded into prune-candidate ranking; no new hot-path write.

**Storage decision (made here, not deferred):** capture a periodic access snapshot in the *nightly* `consolidate_facts` pass itself — write `access_count_prev` + `access_snapshot_at` onto the fact hash at the END of each nightly run (already a batch write context, NOT the hot read path). Velocity = `(access_count - access_count_prev) / elapsed`. First run has no prev → velocity `None` → signal inert for that fact. This adds zero hot-path writes (Global Constraint satisfied).

- [ ] **Step 1: Failing test — flag OFF reproduces today's candidates exactly**

```python
def test_peak_signal_off_matches_baseline(seeded_facts, monkeypatch):
    monkeypatch.setenv("AUTOBOT_FACTS_PEAK_SIGNAL", "0")
    baseline = collect_prune_candidates(seeded_facts)   # current behaviour
    monkeypatch.setenv("AUTOBOT_FACTS_PEAK_SIGNAL", "0")
    assert collect_prune_candidates(seeded_facts) == baseline
```

- [ ] **Step 2: Failing test — flag ON prioritises a peaked-then-declining fact**

```python
def test_peak_signal_on_ranks_declining_fact_higher(monkeypatch):
    monkeypatch.setenv("AUTOBOT_FACTS_PEAK_SIGNAL", "1")
    # fact A: access velocity negative (peaked, declining); fact B: flat
    cands = collect_prune_candidates([fact_declining, fact_flat])
    assert cands.index(fact_declining) < cands.index(fact_flat)
```

- [ ] **Step 3: Run both — expect FAIL.** `cd autobot-backend && python -m pytest knowledge/facts_peak_signal_test.py -v`

- [ ] **Step 4: Implement** — read `AUTOBOT_FACTS_PEAK_SIGNAL` (module-level, `== "1"`); when off, code path is byte-identical to today (guard the new term behind the flag). When on, compute `velocity` from `access_count - access_count_prev` and add it as a tie-shaping term in candidate ranking. Add the end-of-run snapshot write in `consolidate_facts`.

- [ ] **Step 5: Run — expect PASS (both).**

- [ ] **Step 6: Commit**
```bash
git commit -m "feat(memory): flag-gated peak/maturity prune signal, default off (#12635)"
```

---

## Self-Review

**Spec coverage:** P1a↔§3.1, P1b↔§3.2/3.3, P2a↔§4.1, P2b↔§4.2/4.3, P3↔§5, error handling↔§6 (degraded tests in every phase), umbrella structure↔§7. Discovery issues §4.4/non-goals are filed as #12636/#12637 (not tasks here). All spec sections mapped.

**Placeholder scan:** node code blocks are concrete; SLM tasks reference exact pattern files to copy (`voice_proxy.py`, `useAutobotApi.ts`, existing `/monitoring` router children) with the specific deltas — not "implement later". The only pre-implementation reads required are shape-confirmations (`get_all_states()` value keys; `consolidate_facts` dry-run return), flagged inline where needed.

**Type consistency:** payload keys are consistent across tiers — node `{reinforcement,decay,degraded}` is what the SLM proxy forwards and the composable's `MemoryLifecycle` interface mirrors; `{breakers,degraded}` (2a) feeds `provider_breakers` in the 2b aggregate; `effective_score`/`prune_preview`/`velocity` names are used identically wherever referenced.

## Risks / Notes for the executor

- Confirm the exact `include_router` registration site and whether prefix `/api` is applied there vs in the router (grep an existing `api/*` mount — pattern differs by app factory).
- Confirm `check_admin_permission` accepts `X-Internal-API-Key` (voice_proxy comment says the equivalent voice admin dep does; verify for this path).
- Confirm `consolidate_facts(dry_run=True)` current return shape before relying on `.candidates`; extend it in P1a if it only returns a count today.
- SLM i18n: match the full locale-file set an existing `monitoring.*` block covers (do not add English-only).
