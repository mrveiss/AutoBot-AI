<!--
Copyright 2025-2026 mrveiss
SPDX-License-Identifier: Apache-2.0
-->
# LLC Module Ship Report (#9861)

Mission: make the LLC module functional end-to-end on `Dev_new_gui`. Backend is
canonical (RULE ZERO) — frontend rewired to real routes; one read-only endpoint
added by explicit exception; missing-backend features flagged off; the core loop
proven by an e2e test; a blocking CI gate added.

## Starting state
After rebasing onto the latest `Dev_new_gui` (PR **#9862** had just landed and
already fixed 9 of the original 16 unwired LLC calls — activity, agents/status,
approvals/pending, approvals/{id}/approve→decide, budgets→budget, goals/{id}/items→tasks,
heartbeat-runs, work-items/{id}/activity, work-items/{id}/artifacts), **7 LLC
frontend calls remained unwired**. All 7 are now resolved.

## PHASE 1 — Rewired paths (old → new)

| View | Old call (404) | Resolution | Commit |
|---|---|---|---|
| `OrgChart.vue` | `GET /api/llc/org-chart` | `GET /api/llc/companies/{id}/org-chart` (**new** read-only endpoint) | cefaf8c |
| `OrgChart.vue` | `POST /api/llc/agents/{id}/{action}` | `POST /api/llc/companies/{id}/controls/agents/{id}/pause` \| `/resume` (explicit literals) | cefaf8c, 685fbc0 |
| `HeartbeatMonitor.vue` | `GET /api/llc/agents${qs}` (unresolvable literal) | `GET /api/llc/agents?company_id=…` (inlined query) → real `GET /api/llc/agents` | a46ffc7 |
| `SubCompanyTree.vue` | `GET /api/llc/companies/tree` | `GET /api/llc/companies/` (roots) + `GET /api/llc/companies/{id}/tree` per root, composed client-side | 7023a52 |
| `GoalTree.vue` | `GET /api/llc/goals/tree` | `GET /api/llc/goals?company_id=…` (flat) + client-side tree from `parent_goal_id` | e91e019 |
| `CompanyDashboard.vue` | (company context never resolved) | resolves company via `useLlcCompanyContext`; WS now uses reactive `wsUrl` | cfdacd2 |

### The one added backend endpoint (RULE ZERO exception — flagged)
`GET /api/llc/companies/{company_id}/org-chart` (`autobot-backend/llc/api/companies.py`, commit 360b287).
**Read-only composition only** — no new persistence. It joins existing models:
`agent_org_nodes` (hierarchy/title/role) + `llc_agent_budgets` (budget) + latest
`llc_heartbeat_runs` (liveness/status), and assembles a forest from the
self-referencing `reports_to` edges. Tenant access enforced via
`require_org_context`. This is the permitted read-only-composition exception to
backend-canonical wiring, as authorized in the mission brief.

### Company-context decision (resolves #9861 root blocker)
The LLC company-scoped views are reached from a top-level nav entry
(`/llc/dashboard`) that carries no `:companyId`, so the id must be resolved at
runtime. Introduced `useLlcCompanyContext` (`autobot-frontend/src/composables/llc/`)
— resolution order: **route param `:companyId` → `?company=` query → first company
from `GET /api/llc/companies/`** — mirroring the backend, which scopes to the
caller's org when `company_id` is omitted. Used by OrgChart, GoalTree, and
CompanyDashboard. No routes were moved (lower risk; no nav regressions).

## Formerly flagged-off features — now LIVE (#9861 backends + #10040 wiring)
Both backends shipped in #9861 (PR #10034) and were wired up in #10040; the
`import.meta.env` feature flags were removed (features are unconditionally on).

| Feature | Backend | Behaviour |
|---|---|---|
| Backlog drag-reorder persistence | `POST /api/llc/companies/{id}/backlog/reorder` | rows draggable; full desired order POSTed, reverts on failure |
| AC suggestion | `POST /api/llc/work-items/suggest-ac` | "Suggest ACs" button populates advisory ACs; empty on LLM-down |

## PHASE 2 — e2e proof (definition of "working")
`autobot-backend/llc/tests/test_llc_e2e_loop.py` (+ `_e2e_harness.py`), commit 6022b27.

- **Result: `1 passed in ~2.7s`** — deterministic across repeated runs.
- **Hermetic**: httpx against the real LLC routers, real DB session (in-memory
  SQLite), auth dependency-overridden. **No Postgres, no Redis, no network.**
  (App path: minimal-mount of the real routers — `create_app()` can't boot
  in-process because its lifespan hard-requires Postgres/Redis; documented in the
  test.)
- **Loop covered**: create company → hire agent → create work item → record run +
  cost → checkout → handoff-to-human → review-gate approve → work item **DONE** →
  budget reflects cost (`budget_spent == 0.28`, `tokens_spent == 150000`, read
  back from the DB row, not Redis).
- **Steps seeded directly via the session** (no usable public endpoint — filed as
  discoveries): agent hire (`AgentOrgNode` — see #9899), per-agent budget row
  (see #9901), heartbeat run row (scheduler-written by design). All **public**
  loop steps go through real endpoints.

## PHASE 3 — Gate
- **LLC-scoped audit**: `scripts/audit_api_wiring.py` gained `--only-prefix` to
  gate one module while pre-existing repo-wide findings stay tracked separately.
  `--openapi … --only-prefix /api/llc --fail-on-unwired` → **exit 0** (0 unwired
  `/api/llc` calls).
- **Blocking CI**: `.github/workflows/llc-contract.yml` — job 1 dumps the real
  OpenAPI and fails on any unwired `/api/llc` call; job 2 runs the e2e test. Both
  blocking (the repo-wide `api-wiring.yml` stays non-blocking for its tracked
  false-positives). Uses absolute `--openapi`/`--dump-openapi` paths to avoid the
  dump's chdir-into-backend cwd trap.
- **`gen:types` — deferred (documented).** `npm run gen:types` targets a **live
  backend** (`http://127.0.0.1:8001/openapi.json`) and `openapi-typescript` is not
  installed in this environment. Regenerating the 120k-line canonical
  `src/types/generated/api.ts` from a local partial dump would produce a massive,
  divergent, unreviewable diff and risk corrupting the spec. The new org-chart
  type lands on the next live-backend `gen:types` (deploy/CI). The **audit** is
  the binding contract gate; the touched views use minimal local interfaces for
  the new shapes.

## Deferred / out of scope (filed in GitHub)
- **#9899** — `AgentOrgNode` ORM model out of sync with `agent_org_nodes` migration columns (hire endpoint INSERTs unmodelled columns).
- **#9900** — two unmounted routers flagged by the audit: `analytics_engagement.py` (consumed by the frontend → silent dead feature) + `transcripts.py`. Non-LLC.
- **#9901** — no public endpoint to provision a per-agent LLC budget.
- **#9861 (parent)** — still tracks: backlog-reorder + suggest-ac backends, org-chart budget/assigned-count enrichment.
- Non-LLC unwired calls (`/api/{p}/mcp/*`, `/api/ws*`, truncated `code-intelligence`) are the known normalizer false-positives documented in `api-wiring.yml` / tracked under #9851 — not re-filed.

## Commits (branch `llc-ship`)
```
360b287 feat(llc/api): add read-only GET /companies/{id}/org-chart endpoint
cefaf8c fix(llc/frontend): wire OrgChart to real org-chart + controls routes
a46ffc7 fix(llc/frontend): wire HeartbeatMonitor agents query
7023a52 fix(llc/frontend): build company hierarchy from real routes
e91e019 fix(llc/frontend): build goal tree from flat /api/llc/goals
3d4f81b fix(llc/frontend): feature-flag off backlog reorder + AC suggestion
cfdacd2 fix(llc/frontend): resolve company context on the dashboard landing
685fbc0 fix(llc/frontend): inline controls pause/resume paths to satisfy audit
6022b27 test(llc): e2e test for the core LLC loop
e9f050d ci(llc): blocking LLC contract gate — scoped wiring audit + e2e
```
