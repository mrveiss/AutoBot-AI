# Knowledge Health Consolidation — Design

**Date:** 2026-07-10
**Status:** Approved by owner (design phase)
**Scope:** Frontend UI/navigation only — no backend or API changes.
**Companion spec:** `2026-07-10-knowledge-browser-consolidation-design.md`
(document browser consolidation; same sweep-and-remove route pattern).

## Problem

Three Knowledge pages plus one tab duplicate admin/health functionality:

| Surface | Component | Lines | Purpose |
|---|---|---|---|
| `/knowledge/maintenance` | `src/components/knowledge/KnowledgeMaintenance.vue` | ~750 | Health dashboard, dedup, orphans, cleanup, backup, history |
| `/knowledge/stats` | `src/components/knowledge/KnowledgeStats.vue` | ~1700 | Vector DB stats, charts, tag cloud, activity, optimize/reindex |
| `/knowledge/verification` | `src/components/knowledge/KnowledgeVerificationQueue.vue` | ~800 | Source approve/reject queue with bulk ops |
| `/knowledge/manage` → Advanced tab | inside `KnowledgeEntries.vue` | — | System knowledge, failed vectorizations, man pages, **duplicate** dedup + orphan managers |

Confirmed duplication:

1. **DB stats** (total facts, total vectors, DB size, RAG/index health) are
   rendered on both Maintenance and Stats, fetched from two different
   endpoints (`GET /api/knowledge-maintenance/health/dashboard` vs
   `store.refreshStats()` → knowledge stats API).
2. **`DeduplicationManager.vue` and `SessionOrphanManager.vue`** are rendered
   in full on both Maintenance and Manage → Advanced.
3. **Activity timelines** exist on both Maintenance (maintenance history)
   and Stats (recent document activity) — same UI pattern, different events.
4. **Vectorization status** is monitored on both Maintenance and Stats.

## Decisions (owner-approved)

1. **Manage page:** Advanced tab is removed; its tools move to the
   consolidated interface. Manage keeps Upload + Manage tabs only.
2. **Layout:** overview strip + task tabs (Analytics / Verification / Tools).
3. **Naming:** route **`/knowledge/health`**, sidebar entry **"Health"**.
4. Old routes removed outright (no redirects); all in-code references
   updated — same rule as the browser consolidation.

## Design

### 1. Route & navigation

- New route **`/knowledge/health`**; remove `/knowledge/maintenance`,
  `/knowledge/stats`, `/knowledge/verification` from `src/router/index.ts`.
- Sidebar (`KnowledgeView.vue`): remove the Statistics (Analytics section),
  Verification, and Maintenance (Manage section) entries; add one
  **Health** entry.
- Reference sweep: update every reference to the three old paths
  (router, sidebar, docs; exploration found no `router.push` call sites).
  Completion gate: grep returns zero matches for the old paths.
- Deep-link: `?tab=analytics|verification|tools` (default: `analytics`).
- **Canonical component:** `KnowledgeMaintenance.vue` is renamed to
  `KnowledgeHealth.vue` (it already owns the health dashboard) and absorbs
  the other two views. `KnowledgeStats.vue` and
  `KnowledgeVerificationQueue.vue` are deleted after absorption. No
  "Unified"/"Consolidated" variant names.

### 2. Overview strip (single data source)

Always-visible header strip fed by **one API call**:
`GET /api/knowledge-maintenance/health/dashboard` (already returns stats,
quality score + dimensions, issues, recommendations).

- Shows: total facts, total vectors, DB size, quality score, RAG/index
  status, critical/warning issue counts (expandable to recommendations
  and quality-dimension bars).
- The Stats page's duplicate fetch of the same numbers via
  `store.refreshStats()` is dropped **from this page** (the store and its
  API remain untouched for other consumers).
- Refresh-all action refreshes the strip plus the active tab.

### 3. Tabs

- **Analytics** — vector category distribution chart, docs-by-category and
  docs-by-type charts, tag cloud, document change feed, export-stats and
  generate-report actions. The two duplicate timelines merge into **one
  activity feed** with event-type filter chips (maintenance events ·
  document lifecycle events); this is a frontend merge of both existing
  data sources — no backend change.
- **Verification** — tab label carries a pending-count badge. The entire
  existing queue moves as-is: autonomous/collaborative mode toggle, stats
  bar (pending, approved/rejected today, quality threshold), bulk
  approve/reject with select-all, source cards with quality badges,
  pagination.
- **Tools** — the single canonical home for every admin tool, each rendered
  in exactly one place:
  - From Maintenance: `DeduplicationManager`, `SessionOrphanManager`,
    `CleanupStatistics`, `BackupManager`.
  - From Manage → Advanced: `SystemKnowledgeManager`,
    `FailedVectorizationsManager`, `ManPageManager`.
  - From Stats actions: optimize DB, reindex.

### 4. Manage page cleanup

`/knowledge/manage` (`KnowledgeEntries.vue`) keeps **Upload + Manage** tabs
only. The Advanced tab and its tool imports are removed (the tool
components themselves move, not get deleted). The Stats page's existing
router-link to `/knowledge/manage` survives via the sweep (target route
still exists).

### 5. Backend follow-up (out of scope)

The endpoint-level duplication (`/api/knowledge-maintenance/health/dashboard`
vs the knowledge stats API returning overlapping numbers) is **not**
addressed here. A discovery issue will be filed for backend endpoint
dedupe, per repo rules.

### 6. Error handling

- Each tab keeps its existing per-composable error handling and toasts.
- Overview-strip fetch failure shows the existing health-error state
  without blocking tab content.
- Unknown `?tab=` value falls back to the default tab.

### 7. i18n

- Reuse existing `knowledge.maintenance.*`, `knowledge.stats.*`, and
  `knowledge.verification.*` keys wherever the UI element survives.
- New keys (Health nav label, tab labels, merged-feed filter chips) added
  to **all 11 locales**. No hardcoded UI strings.

### 8. Testing & verification

- `vue-tsc --noEmit -p tsconfig.app.json` clean.
- Component tests: tab switching, `?tab=` deep links, pending-count badge,
  merged activity feed filtering, verification bulk actions still guarded.
- Grep gate: zero references to `/knowledge/maintenance`,
  `/knowledge/stats`, `/knowledge/verification` outside git history.
- Existing lint gate (`--max-warnings 0`) stays green.

## Out of scope

- Backend/API changes of any kind (discovery issue filed instead).
- The Upload and Manage tabs of `/knowledge/manage`.
- Other Knowledge sidebar pages (Browser, Transcriber, Research, Vector
  Store, Graph, …).
- Redesign of the individual tool components (they relocate unchanged).
