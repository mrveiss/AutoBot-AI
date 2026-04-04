# Codebase Analytics Test Suite Refactor (#1418)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the codebase analytics page to run all scans sequentially with full progress tracking, fix misplaced API endpoints, make bug prediction use batched scanning, and extract common test utilities.

**Architecture:** The 380KB CodebaseAnalytics.vue currently fires 16+ analytics scans in parallel via Promise.all across 4 phases. This refactor introduces a sequential scan runner composable (useAnalyticsScanRunner) that executes scans one-by-one with a progress bar showing pending/running/completed/failed status. Bug prediction will be converted to use useBackgroundTask (like PatternAnalysis.vue). Cross-language pattern endpoints will be verified against actual router paths.

**Tech Stack:** Vue 3 + TypeScript, FastAPI (Python), existing composables (useAnalyticsFetch, useBackgroundTask)

**Key Files:**
- Frontend: autobot-frontend/src/components/analytics/CodebaseAnalytics.vue (380KB, main component)
- Frontend: autobot-frontend/src/components/analytics/PatternAnalysis.vue (reference for visual style)
- Frontend: autobot-frontend/src/composables/useAnalyticsFetch.ts (existing fetch composable)
- Frontend: autobot-frontend/src/composables/useBackgroundTask.ts (existing background task composable)
- Frontend: autobot-frontend/src/composables/usePatternAnalysis.ts (reference for composable pattern)
- Backend: autobot-backend/api/analytics_bug_prediction.py (bug prediction API)
- Backend: autobot-backend/api/codebase_analytics/endpoints/cross_language_patterns.py (cross-language API)
- Backend: autobot-backend/api/codebase_analytics/api_endpoint_scanner.py (endpoint scanner)
- Backend: autobot-backend/initialization/router_registry/analytics_routers.py (router registry)
- Backend: autobot-backend/api/analytics.py (parent analytics router, includes analytics_cost)

---

## Context: Current Architecture

### How Scans Load Today
loadCodebaseAnalyticsData() (line ~4291 in CodebaseAnalytics.vue) fires scans in 4 phases:
- Phase 1 (awaited): getCodebaseStats(), getProblemsReport()
- Phase 2 (fire-and-forget): loadDeclarations(), loadDuplicates(), loadHardcodes(), loadChartData()
- Phase 3 (fire-and-forget): loadDependencyData(), loadImportTreeData(), loadCallGraphData(), loadConfigDuplicates(), loadApiEndpointAnalysis()
- Phase 4 (fire-and-forget): loadBugPrediction(), loadSecurityScore(), loadPerformanceScore(), loadRedisHealth(), loadEnvironmentAnalysis(), loadOwnershipAnalysis(), getCrossLanguageAnalysis()

Phases 2-4 use Promise.all(...).catch() -- failures are silently logged.

### Router Path Chain
- analytics_routers.py registers api.analytics at prefix /analytics and api.codebase_analytics at prefix /analytics/codebase
- analytics.py includes sub-routers: analytics_cost.router (prefix /cost), analytics_agents.router, etc.
- analytics_bug_prediction.py has APIRouter(prefix="/bug-prediction") registered at prefix /analytics -> full: /api/analytics/bug-prediction/...
- codebase_analytics/router.py includes sub-routers without extra prefixes -> /api/analytics/codebase/...
- Cross-language endpoints: @router.post("/cross-language/analyze") under codebase_analytics -> /api/analytics/codebase/cross-language/...

### Orphaned Endpoint Issue
The API endpoint scanner correctly detects new endpoints from analytics_cost.py (#1401: /by-agent, etc.) as "orphaned" because the frontend has not been built to call them yet -- expected behavior, not a scanner bug.

---

## Task 1: Create useAnalyticsScanRunner Composable

**Files:** Create: autobot-frontend/src/composables/useAnalyticsScanRunner.ts

Core utility: sequential scan runner with progress tracking, logging, and per-scan status.

See composable code in implementation -- follows same pattern as useBackgroundTask.ts and useAnalyticsFetch.ts. Key interfaces: ScanDefinition (id, label, run, skip?), ScanResult (id, label, status, error?, durationMs?). Returns reactive state: results, running, currentScanId, completedCount, failedCount, totalCount, progress, runAll(), reset().

---

## Task 2: Add Scan Progress Bar to CodebaseAnalytics.vue

**Files:** Modify: autobot-frontend/src/components/analytics/CodebaseAnalytics.vue

Import useAnalyticsScanRunner, add scanRunner instance. Add progress bar template showing each scan with status icons (spinner for running, check for completed, times for failed, clock for pending). Style matches PatternAnalysis.vue mini-progress pattern.

---

## Task 3: Refactor loadCodebaseAnalyticsData to Use Sequential Scan Runner

**Files:** Modify: CodebaseAnalytics.vue (lines 4291-4341), en.json

Replace 4 Promise.all phases with single scanRunner.runAll() call listing all 17 scans. Add i18n keys: runningScans, scansComplete, loadPartialFailed, loadComplete.

---

## Task 4: Refactor runFullAnalysis to Use Scan Runner

**Files:** Modify: CodebaseAnalytics.vue (lines 6071-6130)

Replace manual step tracking with scanRunner.runAll() for indexing, pattern analysis, cross-language analysis.

---

## Task 5: Verify All API Endpoint Paths

Audit each frontend URL against backend router chain. Key concern: /analytics/codebase/analytics/... URLs have extra /analytics segment -- verify correct or fix.

---

## Task 6: Convert Bug Prediction to Background Task with Batching

Backend: Add POST /analyze (background task), GET /status/{task_id}, POST /tasks/clear-stuck to analytics_bug_prediction.py. Add batched analysis processing files in groups of 50 with progress callbacks.

Frontend: Replace useAnalyticsFetch with useBackgroundTask for bug prediction. Add progress bar matching PatternAnalysis.vue style.

---

## Task 7: Verify Build and Test

Build frontend, run backend linting, verify no regressions.

---

## Notes for Implementer

1. CodebaseAnalytics.vue is 380KB -- use Edit (not Write) for all changes.
2. Check autobot-backend/utils/background_task_manager.py for existing BackgroundTaskManager.
3. Orphaned analytics_cost endpoints are correct detection -- no scanner fix needed.
4. Keep existing GET /analyze endpoint for backwards compatibility.
5. Pre-commit hooks use --line-length=88 for black.
