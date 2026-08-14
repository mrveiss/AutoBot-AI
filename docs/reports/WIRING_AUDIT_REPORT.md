<!--
Copyright 2025-2026 mrveiss
SPDX-License-Identifier: Apache-2.0
-->

# API Wiring Audit Report (#9851)

Frontend/backend API contract remediation driven by `scripts/audit_api_wiring.py`
in authoritative mode against a `app.openapi()` dump (2055 paths). Branch
`api-wiring-fixes` → `Dev_new_gui`.

## Headline

| Metric | Before | After |
|---|---:|---:|
| Unwired frontend calls | 70 | 19 |
| — of which false positives (audit-tool limits) | — | 14 |
| — of which real, deferred (tracked) | — | 5 |
| Unmounted router modules | 3 | 2 (both false positives) |

51 real unwired calls resolved. The remaining 19 unwired / 2 unmounted are either
audit-tool false positives or deferred items with a clear follow-up (below).

## Fixed

### Backend

1. **`codebase_analytics` router silently unmounted → ~39 dead `/api/analytics/codebase/*` calls.**
   `feature_routers` swallowed two import-time crashes:
   - `ssot_config.codebase_index_embedding_mode` typed `int` (default `0`) but the
     only consumer calls `.lower()` → `AttributeError`. Retyped to `str`
     (`"precompute"`).
   - `scanner.py` annotated `progress_callback: callable | None` using the builtin
     `callable`; PEP-604 unions eval eagerly → `TypeError`. Use `typing.Callable`.

   Result: router mounts 81 paths. (commit `9e87e34c`)

2. **`user_provider_credentials` router never registered + unimportable.** It pulled
   `get_current_user_id`/`get_db_session` from `auth_middleware` (neither exists).
   Wired to `api.user_management.dependencies`; added a `get_current_user_id` UUID
   dependency there; fixed the literal `/api`-doubled prefix; registered in
   `core_routers`. (commit `5f73231c`)

3. **Transcriber double-prefix.** Routes were mounted twice — correctly by
   `core_routers` (`/api/transcriber/*`) and again by `feature_routers` via an
   extension router carrying a full `/api/transcriber` prefix, yielding a dead
   `/api/api/transcriber/*` duplicate. Removed the duplicate registration. (commit `9996f7c3`)

4. **Two minimal LLC read endpoints** (genuinely cheap, mirror existing code):
   - `GET /api/llc/heartbeat-runs` — org-scoped run feed (CompanyDashboard).
   - `GET /api/llc/work-items/{id}/activity` — per-item audit trail (WorkItemDetail),
     tenant-isolated via `require_org_context` (see Security). (commit `d4e658bb`)

### Frontend

5. **LLC views** — pointed at canonical routes, dropped the non-existent
   `{data:{...}}` envelope (ApiClient returns parsed JSON directly):
   CompanyDashboard (`agents/status`→`agents`, `approvals/pending`→`approvals`,
   `budgets`→`budget`, `activity`→`companies/{id}/activity`, approve→`/decide`),
   WorkItemDetail (`artifacts`→`products`, activity→`{items}`), GoalTree
   (`goals/{id}/items`→`/tasks`). (commit `d33d38ba`)

6. **Device pairing panel** — aligned with `mobile_devices.py`:
   `devices/paired`→`/api/devices`, `pairing/generate-code`→`/api/devices/pair-qr`
   (QR challenge token), and removed the dead `pairing/confirm` POST (pairing
   completes mobile-side via `POST /api/devices/pair`; desktop refreshes the
   list). (commit `c5eb9aec`)

### CI

7. **`.github/workflows/api-wiring.yml`** — dumps the spec and runs the audit on
   backend/frontend route changes; static-mode fallback if the app build fails.
   Currently non-blocking (`continue-on-error`) because false positives remain;
   flip to blocking once the audit reaches exit 0.

## Security

The first cut of `GET /api/llc/work-items/{id}/activity` derived the tenant
`company_id` from the requested resource — an IDOR (any user could read any
tenant's work-item activity by guessing an id). Fixed before merge: scope is
now taken from `require_org_context` and the item must belong to the caller's
org (else 404). Flagged by the automated commit security review.

## Deferred (tracked, not fixed here)

These need backend implementation or a frontend redesign beyond path wiring;
filed as **#9861** rather than patched blind. The UI elements should be
feature-flagged off until implemented (no dead buttons).

- **LLC company-context bug.** `CompanyDashboard`/`SubCompanyTree`/`GoalTree`/
  `OrgChart` read `route.params.companyId` on routes that define no such param,
  and there is no company store — so company context is unresolved and these
  views can't drive the (company-scoped) backend. The path/shape fixes above are
  prerequisites; the context plumbing is the blocker.
- **`/api/llc/companies/tree`** (SubCompanyTree) — no global company-tree route;
  build client-side from `/api/llc/companies/` once company context exists.
- **`/api/llc/goals/tree`** (GoalTree) — assemble client-side from flat
  `/api/llc/goals?company_id=` (`parent_goal_id` is present) once context exists.
- **`/api/llc/org-chart`** (OrgChart) — no agent reporting-hierarchy is exposed;
  needs a backend endpoint or a degraded flat-list view. The pause/resume control
  also needs the company-scoped `/companies/{id}/controls/agents/{id}/pause|resume`.
- **`/api/llc/companies/{id}/backlog/reorder`** — write endpoint; `backlog_position`
  exists, needs a bulk-reorder route + ordering semantics.
- **`/api/llc/work-items/suggest-ac`** — needs an LLM-backed acceptance-criteria
  service; only the storage field exists.
- **Pre-existing work_items routes lack tenant checks** (e.g. `/products`,
  `get_work_item`) — noted by the security review; out of scope here, worth a
  hardening pass.

## Known false positives (no action)

The audit's path normalizer flags these; all resolve at runtime:
- Template-literal params: `/api/{server}/mcp/*`, `/api/llc/agents/{id}/{sub}`,
  `/api/analytics/codebase/cross-language/{lang}`, `/api/analytics/codebase/patterns/report/*`.
- Bare base-URL strings: `/api/orchestrator`, `/api/transcriber`, `/api/code-intelligence`.
- Websockets (`/api/ws`, `/api/ws/live`) — FastAPI omits them from OpenAPI.
- Unmounted-router flags for `analytics_engagement` (sub-included via `api.analytics`)
  and `transcripts` (served via the transcriber extension) — both verified mounted.

## Verification

- `app.openapi()` builds: 2055 paths (all changed backend modules import cleanly).
- LLC unit tests: `test_activity_log` + `test_work_item` — 30 passed.
- Types: `npm run gen:types` must run against a fully-provisioned backend; a
  constrained-env regen here was lossy for 77 endpoints (services unavailable),
  so it was not committed. CI/dev should regenerate.
