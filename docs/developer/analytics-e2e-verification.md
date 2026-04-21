# Analytics E2E Verification Checklist

> **Purpose:** walk `/analytics/codebase/{sourceId}` panel-by-panel in a running dev environment to confirm each test section actually displays data end-to-end. Unit tests and `vue-tsc` catch contract drift but cannot catch wiring drift at the template-binding level (bug class behind #5277 / #5340 / #5365).

---

## When to run

- Before releasing a version that touches `autobot-frontend/src/components/analytics/` or `autobot-backend/api/codebase_analytics/`.
- After closing any issue tagged `codebase-analytics`.
- Whenever the backend Redis analytics schema changes.

## How to run

1. Start the stack in dev mode:

   ```bash
   cd autobot-backend && python main.py &
   cd autobot-frontend && npm run dev
   ```

2. Index a real source (not a toy fixture — panels behave differently with sparse data):

   ```bash
   curl -X POST http://localhost:8001/api/analytics/codebase/scan \
     -H 'Content-Type: application/json' \
     -d '{"path": "/home/martins/AutoBot-Ai/AutoBot-AI", "source_id": "autobot-self"}'
   ```

3. Load `/analytics/codebase/autobot-self` in the frontend.

4. For each panel row below: click the `Test …` / `Refresh` button, wait for the toast, record the result.

## Panel-by-panel checklist

Copy this table into a commit message or a tracking issue when running the audit. Replace `YYYY-MM-DD` and `<sha>` with actuals.

| # | Panel | Test button / trigger | Expected result | Tested (date) | Tested (commit) | Result |
|---|---|---|---|---|---|---|
| 1 | AnalyticsProgressSection | automatic on scan | progress bar reflects live scan % | | | |
| 2 | CodebaseOverviewPanel | automatic | file counts + LOC populated | | | |
| 3 | CodebaseChartsSection | **Test Charts** | stacked line chart renders | | | |
| 4 | CodebaseDependenciesPanel | **Test Dependencies** | dependency graph populated (cytoscape) | | | |
| 5 | ProblemsReportSection | **Test Problems** | problems list populated; MD/JSON export works | | | |
| 6 | CodeSmellsSection | **Test Code Smells** | smells grouped by type, counts populated | | | |
| 7 | CodebaseSecurityPanel | **Run Code Intelligence Analysis** | security / performance / redis finding tabs populated (#5365 regression guard) | | | |
| 8 | DuplicatesSection | **Test Duplicates** | similarity buckets populated; loading spinner renders during scan (#5368); MD/JSON export works | | | |
| 9 | DeclarationsSection | **Test Declarations** | type buckets populated; loading spinner renders during scan (#5368) | | | |
| 10 | HardcodesSection (#5277) | **Test Hardcodes** | severity buckets populated; filenames non-empty (#5290 regression guard); MD/JSON export works | | | |
| 11 | CodebaseApiEndpointsPanel | **Test API Endpoints** | backend/frontend coverage %, orphaned endpoints populated | | | |
| 12 | CodebaseCrossLanguagePanel | **Run Cross-Language Analysis** | DTO mismatches / API mismatches counts populated | | | |
| 13 | CodebaseConfigDuplicatesPanel | **Test Config Duplicates** | duplicate config keys listed | | | |
| 14 | CodebaseBugPredictionPanel | **Test Bug Prediction** | risk scores per file populated | | | |
| 15 | CodebaseIntelligenceScoresPanel | **Calculate Health Score** | security / performance / redis score cards populated | | | |
| 16 | CodebaseEnvironmentPanel | **Test Environment** | hardcoded values + recommendations populated (#5367 normalizer guard) | | | |
| 17 | CodebaseOwnershipPanel | **Test Ownership** | bus factor + contributor list populated | | | |

## Result codes

- **OK** — data rendered, export works, no console errors.
- **EMPTY** — scan completed but panel shows zero items *and* the codebase actually has non-zero items for this metric. File a new issue.
- **BROKEN** — console errors, stack traces, 500s, or TS warnings in browser devtools. File a new issue.
- **BLOCKED** — upstream dependency failing (e.g. ChromaDB down, LLM unavailable). Document which.

## Export verification

For every panel with MD/JSON export buttons (rows 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17):

1. Click **MD** → browser downloads `<panel>-<timestamp>.md` → file is non-empty → contains a rendered table.
2. Click **JSON** → browser downloads `<panel>-<timestamp>.json` → valid JSON → fields match `HardcodedValue` / `Duplicate` / etc. canonical shape.

## Follow-up

- Any `EMPTY` / `BROKEN` row should generate a GitHub issue immediately with title `bug(codebase-analytics): <panel> <failure-mode>`.
- Use `/dead-code-audit` and `python3 tools/lint/check_no_orphan_refs.py` to catch the most common orphan-ref + dead-code bug shapes before running this manual checklist.

## Historical results

Append new rows here after each run.

| Run date | Tested commit | Branch | Result summary | Issues filed |
|---|---|---|---|---|
| _(no runs yet)_ | | | | |

## Related

- Issue #5277 (hardcodes panel wired)
- Issue #5290 (HardcodedValue contract normalized)
- Issue #5311 (4 duplicate TS types consolidated)
- Issue #5313 (normalizer integration tests)
- Issue #5349 (orphan-ref audit tooling `tools/lint/check_no_orphan_refs.py`)
- Issue #5365 (3 code-intel findings wired)
- Issue #5367 (env-analysis boundary normalizer)
- Issue #5368 (per-section loading spinners)
- Issue #5369 (component unit tests for Hardcodes/Duplicates/Declarations)
- Issue #5370 (this document)
