# System Lifecycle Observability — Design Spec

**Date:** 2026-07-26
**Status:** Approved design — pending umbrella creation
**Author:** mrveiss
**Type:** Observability feature (phased umbrella)

---

## 1. Motivation

AutoBot runs several independent *lifecycle state machines* that govern its own
behaviour, but most of them are **operationally dark** — no read API, no admin
surface. An operator cannot see what state these subsystems are in without
reading logs or code:

| Subsystem | State machine | Currently surfaced? |
|-----------|---------------|---------------------|
| Memory facts | `unverified → verified → reinforced → prune-eligible` | **No** — no read API anywhere. `memory:consolidate_facts:last_run` has zero readers; `access_count`/`last_accessed`/`_effective_score` invisible; nightly decay/prune ships **inert + dry-run** with no way to preview what it *would* delete. |
| LLM provider breakers | `CLOSED → OPEN → HALF_OPEN` (`circuit_breaker.py`, `get_all_states()`) | **No** — the getter exists but no endpoint exposes it. These are the breakers that gate provider availability. |
| Resilience breakers | `services/resilience/circuit_breaker_manager.py` | Yes — `GET /error-resilience/circuit-breakers`. |
| Provider fallback | fallback-chain hops + degradation | Yes — `GET /api/llm/fallback-status`, `ProviderFallbackView.vue`. |
| Probe health | CONTENT_REACH probe | Yes — `SystemHealthView.vue`. |

The gap: the two most consequential subsystems (memory lifecycle, provider
breakers) are invisible, and **nothing composes** the existing surfaces into a
single operator view. This spec makes all of them observable, admin-only,
read-only, with one behaviour-affecting follow-on (Phase 3) that is flag-gated
off by default.

**Non-goals:**
- No change to memory decay/prune, breaker, or fallback *behaviour* in P1/P2
  (pure read path).
- No unification of the two circuit-breaker managers (filed as a separate
  discovery issue).
- No relocation of the pre-existing `ProviderFallbackView`/`SystemHealthView`
  (they live in `autobot-frontend`; filed as a separate discovery issue).
- Not end-user facing — admin/ops only, preserving the "invisible by default"
  intent of these subsystems.

---

## 2. Architecture

**Placement (two-backend model):** SLM is the control plane; `autobot-backend`
is the managed service. The lifecycle *data* lives on the managed node
(memory facts in the node's Redis; breakers in-process in the node's
`autobot-backend`), but the admin *surface* belongs in SLM. Therefore each
read path is two-tier:

```
┌────────────────────────────┐      ┌──────────────────────────────┐      ┌───────────────────────────┐
│ autobot-slm-frontend       │      │ autobot-slm-backend          │      │ autobot-backend (node)    │
│ /monitoring/lifecycle tab  │─────▶│ lifecycle aggregator         │─────▶│ node read endpoints:      │
│ /monitoring/system tab     │ HTTP │ (calls node via SLM→node     │ HTTP │  GET /api/memory/lifecycle│
│ (Vue, i18n, SLM router)    │◀─────│  client, fleet-aware)        │◀─────│  GET /api/system/breakers │
└────────────────────────────┘      └──────────────────────────────┘      └───────────────────────────┘
```

**Design invariants:**
- **Read-only by construction.** Node endpoints only call existing getters and
  `dry_run=True` code paths. The prune preview literally invokes
  `consolidate_facts(dry_run=True)`, which cannot delete.
- **Consume already-emitted state.** The aggregator never reaches into subsystem
  internals — it calls the node's read endpoints and existing SLM composables.
- **Graceful degradation.** Every read endpoint returns a partial payload with a
  `degraded: true` marker when a dependency (Redis, a node) is unreachable —
  never a 500. Mirrors the in-process fallback in `provider_degradation.py`.
- **Admin-gated.** Node endpoints reuse the existing admin auth dependency;
  SLM routes use the SLM admin guard.

---

## 3. Phase 1 — Memory Lifecycle Observability (LOW risk)

### 3.1 Node endpoint (`autobot-backend`)
New module `api/memory_lifecycle.py`, mounted read-only, admin-gated.

`GET /api/memory/lifecycle` → payload:
- `reinforcement`: top-N reinforced facts and coldest-N facts, each with
  `fact_id`, `quality_score`, `access_count`, `last_accessed`, and the computed
  `effective_score` (from `essential_story._effective_score`).
- `decay`: `last_run` (reads `memory:consolidate_facts:last_run` — the currently
  unread key), config snapshot (epoch set?, dry-run flag, max-per-run), and a
  **prune preview** = the candidate list `consolidate_facts(dry_run=True)` would
  delete, each with the reason it qualified (unprotected, below quality floor,
  `access_count == 0`, post-epoch, aged-out).
- `degraded`: bool.

Bounded: `N` capped by a query param with a hard server-side max; preview
capped at the existing `MAX_PER_RUN` ceiling.

### 3.2 SLM aggregator (`autobot-slm-backend`)
Thin endpoint that calls the node endpoint via the SLM→node client and returns
the node payload (fleet-aware: single node for now, structured to fan out
later). Degrades to `degraded: true` + empty sections if the node is down.

### 3.3 SLM frontend
`autobot-slm-frontend/src/views/monitoring/MemoryLifecycleTab.vue` under the
`/monitoring` route (new router child + nav entry). Two panels:
- Reinforcement leaderboard (hot facts) + cold-facts table.
- "What decay would prune" table (preview + reasons) with a clear
  "dry-run — nothing is deleted" affordance.
- i18n across all SLM locales.

### 3.4 Tests
- Node: payload shape; **prune preview deletes nothing** (assert store unchanged);
  hot/cold ordering; degraded path when Redis absent.
- SLM: aggregator returns node payload; degraded path when node absent.

---

## 4. Phase 2 — Unified Lifecycle Dashboard (MEDIUM risk)

### 4.1 Node endpoint
`GET /api/system/breakers` exposing `circuit_breaker.get_all_states()` (the LLM
provider breakers — the newly-surfaced dark subsystem). Admin-gated, read-only.

### 4.2 SLM aggregator
`GET /api/system/lifecycle` — composes, per node: memory summary (P1),
provider-breaker states (4.1), resilience breakers (reuse
`/error-resilience/circuit-breakers`), fallback (reuse `/api/llm/fallback-status`),
health (reuse probe health). Each section independently degradable.

### 4.3 SLM frontend
`autobot-slm-frontend/src/views/monitoring/SystemLifecycleTab.vue` — one page of
cards:
- Memory card (embeds/links the P1 tab's summary — reused, not duplicated).
- Provider-breaker card (state per provider, OPEN/HALF_OPEN highlighted).
- Fallback + health cards (link out to existing surfaces).
- i18n across all SLM locales.

### 4.4 Discovery issue (filed, not implemented here)
Two circuit-breaker managers exist (`circuit_breaker.py` vs
`services/resilience/circuit_breaker_manager.py`). Flag for canonical
unification — out of this scope.

### 4.5 Tests
- Node: `/api/system/breakers` returns all breaker states; degraded path.
- SLM: aggregate composes all sections; a single failing section does not fail
  the whole payload (partial + `degraded`).

---

## 5. Phase 3 — Peak/Maturity Signal (MEDIUM risk, behaviour-affecting)

Adds a **usage-velocity signal** — a fact whose access rate has peaked and is now
declining — to sharpen prune targeting. Purely node-side.

- **Where:** prune-candidate scoring in `consolidate_facts`
  (`knowledge/facts.py`), and optionally the recency/usage blend in
  `essential_story._effective_score`.
- **Signal:** derive a velocity/trend from `access_count` deltas over time
  (requires a lightweight last-window snapshot; exact storage decided in
  planning — must not add a hot-path write).
- **Gating:** `AUTOBOT_FACTS_PEAK_SIGNAL` (or similar), **default OFF**, matching
  the memory epic's conservative convention (decay/prune already ships inert +
  dry-run). Flag OFF must reproduce current behaviour byte-for-byte.
- **Observability tie-in:** the signal's effect is visible in P1's prune preview
  *before* anyone enables it — operators can watch what it would change.

### Tests
- Signal computed correctly from a synthetic access history.
- Flag OFF ⇒ identical prune candidates and identical `_effective_score`
  ordering as today (regression guard).

---

## 6. Error Handling (all phases)

- Redis unreachable → node endpoint returns empty sections + `degraded: true`.
- Node unreachable → SLM aggregator returns `degraded: true` + whatever sections
  it could reach.
- Prune preview failure → empty preview, never raises.
- No endpoint in this spec performs a write; a write attempt is a bug.

---

## 7. Umbrella / Child Structure

One umbrella issue, sequenced children (one PR each), implemented only while
open PRs < 5:

1. **P1a — Node: `GET /api/memory/lifecycle`** (reinforcement + dry-run prune preview) + tests.
2. **P1b — SLM: aggregator + `MemoryLifecycleTab.vue`** (router, nav, i18n) + tests.
3. **P2a — Node: `GET /api/system/breakers`** (provider breaker states) + tests.
4. **P2b — SLM: `GET /api/system/lifecycle` aggregate + `SystemLifecycleTab.vue`** (composes P1 card + breakers + fallback/health links) + tests.
5. **P3 — Node: peak/maturity usage-velocity signal** (flag OFF default) + regression tests.

Plus two **discovery issues** (filed, not in scope): two-breaker-manager
unification; relocate `ProviderFallbackView`/`SystemHealthView` into SLM.

Labels per convention: `observability`, `feature`, `backend`/`frontend`,
`priority: medium`.

---

## 8. Verification (acceptance)

- Enable memory instrumentation on a test node → `GET /api/memory/lifecycle`
  returns reinforcement stats and a non-empty dry-run prune preview; the fact
  store is provably unchanged after the call.
- SLM monitoring `/monitoring` shows the Memory Lifecycle tab (P1) and System
  Lifecycle tab (P2) rendering live node data; a downed node degrades the UI
  gracefully (no crash, `degraded` shown).
- Trip a provider breaker (mock repeated failures) → `/api/system/breakers`
  shows it OPEN; SLM breaker card reflects it.
- With `AUTOBOT_FACTS_PEAK_SIGNAL` off, prune candidates are identical to
  pre-P3 behaviour (regression test green).

## 9. Model Used

Opus 4.8 (research, audit, design).
