# Knowledge Health Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge `/knowledge/maintenance`, `/knowledge/stats`, `/knowledge/verification`, and the Manage page's Advanced tab into one page at `/knowledge/health` (always-visible overview strip + Analytics / Verification / Tools tabs), remove the three old routes, and update every in-code reference.

**Architecture:** `KnowledgeMaintenance.vue` is renamed to `KnowledgeHealth.vue` (it already owns the health-dashboard strip) and becomes a thin shell: overview strip + tab bar. Two new children (`KnowledgeHealthAnalytics`, `KnowledgeHealthTools`) absorb the Stats page and the admin tools; the self-contained `KnowledgeVerificationQueue.vue` is mounted as the Verification tab (kept as a component — mounting it *is* the absorption; re-authoring it would duplicate 800 working lines). `KnowledgeStats.vue` dissolves across strip/Analytics/Tools and is deleted. Frontend-only.

**Tech Stack:** Vue 3 `<script setup>` + TypeScript, vue-router 4, vue-i18n, Vitest.

**Spec:** `docs/superpowers/specs/2026-07-10-knowledge-health-consolidation-design.md`
**Sibling precedent:** browser consolidation #11526 / PR #11553 (same sweep-and-remove pattern).

## Global Constraints

- Branch target: `Dev_new_gui` (branch AFTER PR #11553 merges — it rewrote `KnowledgeView.vue` and `router/index.ts`; all line numbers below are anchors, re-locate by the quoted text).
- Work in `.worktrees/issue-11558/`; commits `<type>(scope): <description> (#issue)`. NO commit trailers. Never `--no-verify`.
- No `Enhanced/Unified/Consolidated/V2` names. No hardcoded UI strings (new keys → ALL 11 locales `src/i18n/locales/{ar,de,en,es,fa,fr,he,lv,pl,pt,ur}.json`). No `console.*` (use `createLogger`). No raw hex colors in styles — the Stylelint Token Guard flags them; use `var(--token)` without hex fallbacks (see #11515).
- Commands run from `autobot-frontend/` in the worktree; symlink node_modules from the main tree if missing (never commit it).
- Gates: `npx vue-tsc --noEmit -p tsconfig.app.json` · `npx vitest run` · `npm run lint` · stylelint spot-check on new/renamed files (`npx -y -p stylelint@16 -p postcss-html@1.6 stylelint <files>`).
- Spec deviation (approved rationale above): `KnowledgeVerificationQueue.vue` is kept as a component and mounted in the Verification tab instead of being deleted.

## Verified structure (2026-07-10, pre-#11553-merge line refs)

- **KnowledgeMaintenance.vue (754 l):** header 3-23; health dashboard 25-136 (stats cards 41-79, quality dims 82-103, issues 106-118, recommendations 121-129); maintenance actions 138-162 (renders `DeduplicationManager`, `SessionOrphanManager`, `CleanupStatistics`, `BackupManager`); maintenance history 164-192 — **a "future enhancement" stub with no data source: drop it**, the merged feed comes from Stats' real sources. Script: `useKnowledgeMaintenance()` → `{ healthDashboard, isLoadingHealth, loadHealthDashboard }` (`HealthDashboard = { status, last_updated, stats: { total_facts, total_vectors, db_size, categories, embedding_cache }, quality: { overall_score, dimensions, critical_issues, warnings }, top_recommendations }`).
- **KnowledgeStats.vue (1692 l):** error banner 3-10; vector overview cards 25-74 (duplicates the strip → NOT carried over); vectorization notice 77-91 (→ strip, under the status area); vector categories distribution 94-117 (→ Analytics); vector index health 120-174 (→ strip, condensed to the RAG/index status + expandable details); DocumentChangeFeed 178-184 (→ Analytics); overview cards 187-254 (documents/categories/tags/storage → Analytics as a compact row; facts card dropped as strip-duplicate); charts 257-296 (→ Analytics); recent activity 299-317 (→ Analytics feed); tag cloud 320-338 (→ Analytics); system-knowledge nav card 341-362 (**drop** — its target content now lives in the Tools tab of this very page); actions 365-378: `exportStats` 606-638 + `generateReport` 664-698 → Analytics; `optimizeKnowledge` 640-662 (controller.cleanupKnowledgeBase + reindexKnowledgeBase) → Tools. Script: `useKnowledgeStore` (`categoryCount, documentCount, documents, categories, allTags, stats, refreshStats`), `useKnowledgeStats` (`categoryFactCounts, refreshCategoryFacts`), `useKnowledgeController`, `refreshVectorStats()` 761-822.
- **KnowledgeVerificationQueue.vue (799 l):** fully self-contained (own store wiring, repository calls, bulk selection, pagination). Renders unchanged inside a tab.
- **KnowledgeEntries.vue:** tab buttons 4-26 (`'upload' | 'manage' | 'advanced'` at line 476); advanced block 32-46 rendering `SystemKnowledgeManager`, `DeduplicationManager`, `SessionOrphanManager`, `FailedVectorizationsManager`, `ManPageManager` (imports 446-450, ManPageManager from `@/components/manpage/`).
- **Sidebar (KnowledgeView.vue, pre-#11553 numbering):** Manage divider 154-155; manage 158-168; verification 170-180; maintenance 206-217; Analytics divider 236-237 holding ONLY stats 240-249 → divider becomes empty and is removed.
- **Router:** verification 241-249; stats 290-298; maintenance 399-407.
- **Other references:** route names only in router + sidebar; `KnowledgeStats` also imported by `KnowledgeManager.vue` componentMap (`stats:` tab) and exported from `components/knowledge/index.ts`; `config/routes.ts` has a `knowledge-stats` child entry. No `router.push` call sites. Backend API paths under `/api/knowledge-maintenance/*` are NOT route references.
- **i18n:** reuse `knowledge.maintenance.*`, `knowledge.stats.*`, `knowledge.verification.*`. New: `knowledge.views.health`, `knowledge.views.healthAriaLabel`, `knowledge.health.tabAnalytics`, `knowledge.health.tabVerification`, `knowledge.health.tabTools`.

---

### Task 0: Worktree + spec/plan commit

- [ ] Confirm PR #11553 is merged into `Dev_new_gui`; then from the repo root:

```bash
git fetch origin Dev_new_gui
git worktree add .worktrees/issue-11558 -b issue-11558 origin/Dev_new_gui
git -C .worktrees/issue-11558 branch --unset-upstream
mkdir -p .worktrees/issue-11558/docs/superpowers/{specs,plans}
cp docs/superpowers/specs/2026-07-10-knowledge-health-consolidation-design.md .worktrees/issue-11558/docs/superpowers/specs/
cp docs/superpowers/plans/2026-07-10-knowledge-health-consolidation.md .worktrees/issue-11558/docs/superpowers/plans/
cd .worktrees/issue-11558 && sed -i 's/#11558/#11558/g; s/issue-11558/issue-11558/g' docs/superpowers/plans/2026-07-10-knowledge-health-consolidation.md
git add docs/superpowers && git commit -m "docs(knowledge): health consolidation spec + plan (#11558)"
```

---

### Task 1: `KnowledgeHealthTools.vue`

**Files:** Create `src/components/knowledge/KnowledgeHealthTools.vue`.
**Interfaces:** No props. Emits none (each manager component is self-contained). Consumes `useKnowledgeController` for optimize/reindex.

- [ ] Template: a `.tools-grid` of sections rendering, in order: `DeduplicationManager`, `SessionOrphanManager`, `CleanupStatistics`, `BackupManager` (imports as in KnowledgeMaintenance.vue:202-205), `SystemKnowledgeManager`, `FailedVectorizationsManager`, `ManPageManager` (imports as in KnowledgeEntries.vue:446-450 — note `ManPageManager` comes from `@/components/manpage/ManPageManager.vue`), plus a "Database actions" section with the optimize-DB button whose handler is `optimizeKnowledge` moved verbatim from KnowledgeStats.vue:640-662 (confirm-dialog + `controller.cleanupKnowledgeBase()` + `controller.reindexKnowledgeBase()`, incl. `useConfirmDialog` usage). Reuse the existing `knowledge.stats.optimizeDb` key for the button.
- [ ] Move the section-layout styles that KnowledgeMaintenance's actions grid used (lines 138-162 region styles) — token-only colors, no hex fallbacks.
- [ ] Gate: `npx vue-tsc --noEmit -p tsconfig.app.json` clean. Commit: `feat(knowledge): health tools tab component (#11558)`.

---

### Task 2: `KnowledgeHealthAnalytics.vue`

**Files:** Create `src/components/knowledge/KnowledgeHealthAnalytics.vue`.
**Interfaces:** No props (owns its data via store/composables, mirroring KnowledgeStats). Consumes `useKnowledgeStore`, `useKnowledgeStats`, `DocumentChangeFeed`, `BasePanel`, `StatusBadge`, `EmptyState`.

- [ ] Move from KnowledgeStats.vue (line refs above), preserving behavior: vector categories distribution chart (94-117 + `refreshCategoryFacts`), compact overview row for documents/categories/tags/storage (from 187-254, dropping the facts card), charts section (257-296), **activity feed** = recent activity (299-317) rendered with event-type filter chips (`all · documents · maintenance` — chips filter the existing `recentActivities` items by their `type` field; new keys not needed if `knowledge.stats.*` already has labels, else add under Task 6), DocumentChangeFeed (178-184), tag cloud (320-338), and an actions row with `exportStats` (606-638) + `generateReport` (664-698) moved verbatim.
- [ ] The component fetches its own data in `onMounted` (the `refreshStats()` part of KnowledgeStats.vue:859-862; the vector-stat mapping `refreshVectorStats` 761-822 moves to the parent strip in Task 3 — only the store-backed pieces used by this tab stay here).
- [ ] Gate: vue-tsc clean. Commit: `feat(knowledge): health analytics tab component (#11558)`.

---

### Task 3: Rename to `KnowledgeHealth.vue` + strip + tab shell

**Files:** `git mv src/components/knowledge/KnowledgeMaintenance.vue src/components/knowledge/KnowledgeHealth.vue`; modify it.
**Interfaces:** Route component for `knowledge-health`; honors `?tab=analytics|verification|tools` (default `analytics`).

- [ ] Keep: header (3-23, retitle via new `knowledge.views.health` key) and the health-dashboard strip (25-136) fed by `useKnowledgeMaintenance` — single API source per spec. Extend the strip's status area with the RAG/index availability condensed from KnowledgeStats' index-health section (120-174): show `RAG available/unavailable` + `index initialized` badges, with the detail fields (redis_db, embedding_model, …) inside an expandable `<details>`. Data: move `refreshVectorStats()` (KnowledgeStats.vue:761-822) here, renamed `loadVectorHealth()`, called from `onMounted` alongside `loadHealthDashboard()`. Show the vectorization-notice warning (77-91) in the strip when `total_facts > 0 && total_vectors === 0`.
- [ ] Remove: maintenance-actions section (moved to Tools) and the maintenance-history stub (164-192) + its i18n-only content (`knowledge.maintenance.maintenanceHistory/noHistory` keys stay in locales, unused — acceptable).
- [ ] Add tab bar (`analytics | verification | tools`; verification label carries a pending-count badge from `useKnowledgeStore().pendingVerificationsTotal`) + tab bodies rendering `KnowledgeHealthAnalytics`, `KnowledgeVerificationQueue`, `KnowledgeHealthTools`. Lazy-render inactive tabs with `v-if` (not `v-show`) so Verification's `onMounted` fetch happens on first open.
- [ ] `?tab=` handling in `onMounted`: `const t = route.query.tab; activeTab.value = (typeof t === 'string' && ['analytics','verification','tools'].includes(t)) ? t : 'analytics'`. Unknown value → default (spec §6).
- [ ] Refresh-all button refreshes the strip (`loadHealthDashboard()` + `loadVectorHealth()`); each tab keeps its own refresh affordances.
- [ ] Gate: vue-tsc clean. Commit: `feat(knowledge): KnowledgeHealth shell — overview strip + analytics/verification/tools tabs (#11558)`.

---

### Task 4: Remove the Manage page's Advanced tab

**Files:** Modify `src/components/knowledge/KnowledgeEntries.vue`.

- [ ] Delete the advanced tab button (19-25), the advanced content block (32-46), the five tool imports (446-450), and narrow `manageTab` to `ref<'upload' | 'manage'>('upload')` (476). If any `manageTab === 'advanced'` guards remain elsewhere in the file, remove them.
- [ ] Gate: vue-tsc clean; `npx vitest run` for any KnowledgeEntries tests. Commit: `refactor(knowledge): remove Manage Advanced tab — tools moved to /knowledge/health (#11558)`.

---

### Task 5: Router, sidebar, sweep, deletion

**Files:** `src/router/index.ts`, `src/views/KnowledgeView.vue`, `src/config/routes.ts`, `src/components/knowledge/KnowledgeManager.vue`, `src/components/knowledge/index.ts`; delete `src/components/knowledge/KnowledgeStats.vue`.

- [ ] Router: replace the maintenance entry with `{ path: 'health', name: 'knowledge-health', component: () => import('@/components/knowledge/KnowledgeHealth.vue'), meta: { title: 'Knowledge Health', parent: 'knowledge' } }`; delete the stats and verification entries.
- [ ] Sidebar: remove verification + maintenance entries and the stats entry; the now-empty **Analytics divider is removed**; add one Health entry under the Manage divider (`to="/knowledge/health"`, active on `$route.name === 'knowledge-health'`, keys `knowledge.views.health` / `knowledge.views.healthAriaLabel`, reuse the maintenance entry's SVG icon).
- [ ] `config/routes.ts`: replace the `knowledge-stats` child entry with `{ path: '/knowledge/health', name: 'knowledge-health', component: 'KnowledgeHealth', description: 'Knowledge health, analytics and tools', icon: 'fas fa-heartbeat' }`.
- [ ] `KnowledgeManager.vue`: componentMap `stats:` → lazy `KnowledgeHealth` import (`const KnowledgeHealth = () => import('./KnowledgeHealth.vue')`); remove the `KnowledgeStats` lazy import.
- [ ] `components/knowledge/index.ts`: replace any `KnowledgeMaintenance`/`KnowledgeStats` exports with `KnowledgeHealth`; keep `KnowledgeVerificationQueue` export.
- [ ] `git rm src/components/knowledge/KnowledgeStats.vue`; delete its stories file if one exists (`ls src/components/knowledge/KnowledgeStats.stories.ts`).
- [ ] Grep gate (zero output):

```bash
grep -rn --include='*.vue' --include='*.ts' -E "knowledge/(maintenance|stats|verification)['\"]|knowledge-maintenance|knowledge-stats|knowledge-verification|KnowledgeMaintenance|KnowledgeStats\b" src/ | grep -vE "api/|knowledge-maintenance/|useKnowledgeMaintenance|useKnowledgeStats|generated|KnowledgeStatsResponse"
```
  (`useKnowledgeMaintenance`/`useKnowledgeStats` composables and `/api/knowledge-maintenance/*` backend paths survive by design.)
- [ ] Gates: vue-tsc clean; full `npx vitest run`. Commit: `feat(knowledge): route /knowledge/health replaces maintenance/stats/verification (#11558)`.

---

### Task 6: i18n — all 11 locales

- [ ] Add to every locale, inside existing objects: `knowledge.views.health` ("Health"), `knowledge.views.healthAriaLabel` ("Knowledge health, analytics, verification and tools"), `knowledge.health.tabAnalytics` ("Analytics"), `knowledge.health.tabVerification` ("Verification"), `knowledge.health.tabTools` ("Tools"), plus feed filter chips if Task 2 introduced them (`knowledge.health.feedAll` "All", `knowledge.health.feedDocuments` "Documents", `knowledge.health.feedMaintenance` "Maintenance"). Translate per locale following neighboring keys.
- [ ] Validate JSON ×11; `npx vitest run src/i18n` (locale-parity) green; vue-tsc clean. Commit: `feat(i18n): knowledge health consolidation keys x11 locales (#11558)`.

---

### Task 7: Full gates + PR

- [ ] `npx vue-tsc --noEmit -p tsconfig.app.json` · `npx vitest run` · `npm run lint` · stylelint spot-check on `KnowledgeHealth.vue`, `KnowledgeHealthAnalytics.vue`, `KnowledgeHealthTools.vue` (0 problems — no hex).
- [ ] Manual smoke: `/knowledge/health` default tab analytics; `?tab=verification` and `?tab=tools` deep links; unknown `?tab=` falls back; strip renders from one fetch; Manage page shows only Upload + Manage.
- [ ] Re-run Task 5 grep gate.
- [ ] PR → `Dev_new_gui` (headings Thinking Path / What Changed / Verification / Model Used, `Closes #11558`); check open-PR count ≤5.

## Self-review notes

- Spec coverage: route/nav/sweep (T5), strip single-source + vectorization notice + RAG status (T3), Analytics incl. merged feed (T2 — maintenance history was a stub, so the "merge" is chips over Stats' real feed; deviation documented), Verification as-is (T3 mounts the kept component — documented deviation), Tools canonical home incl. Manage-Advanced exclusives + optimize/reindex (T1, T4), i18n (T6), gates (T7). Backend endpoint dedupe already filed as #11554.
- Type consistency: tab ids `'analytics'|'verification'|'tools'` used identically in T3 shell, `?tab=` guard, and T6 keys.
- Known risks: line numbers shift after #11553 merges (KnowledgeView.vue, router/index.ts) — anchors quoted for re-location; KnowledgeManager stats-tab retarget keeps the unwired legacy component compiling (#11555 owns its fate).
