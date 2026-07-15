# Datetime Producer Audit — Direct Timestamp Construction Bypassing `time_utils`

> **Status**: Part A of [#5178](https://github.com/mrveiss/AutoBot-AI/issues/5178). Audit only — migration is Part B (this PR does not migrate).
> **Scope**: backend Python files that construct ISO-8601 timestamps directly instead of calling [`autobot_shared.time_utils`](../../../autobot_shared/time_utils.py).
> **Companion audit**: [datetime parsing audit](datetime-parsing-audit.md) (#5169 part B) — established the parser landscape this audit feeds into.

## TL;DR

| Pattern | Sites | Files | Severity |
|---|---|---|---|
| `datetime.utcnow().isoformat()` | **136** | 56 | 🟡 Producer-only correctness — output is **tz-naive** (no `+00:00` suffix); Py 3.12 will deprecate `utcnow()` |
| `datetime.now().isoformat()` | 0 | 0 | (none — clean) |
| `time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())` | 2 | 1 (`conversation_export.py`) | 🟢 Functionally correct — produces `Z` format for export records |
| `time.strftime("%Y-%m-%dT%H:%M:%S")` (no tz, no gmtime) | 1 | 1 (`man_page_knowledge_integrator.py:96`) | 🔴 **Real bug** — local time, naive, mislabeled as UTC |
| **Total** | **139** | **57** | |

136 of 139 sites are mechanically migratable to `utc_timestamp()`. The 3 outliers need targeted handling (1 hard bug fix, 2 careful export-format decisions).

---

## Method

```bash
grep -rn "datetime\.utcnow()\.isoformat\|datetime\.now()\.isoformat\|time\.strftime.*%Y-%m-%dT" \
  autobot-backend autobot_shared --include="*.py" \
  | grep -v "_test.py\|__pycache__\|time_utils.py\|workflow_versioning.py"
```

Excluded:
- `_test.py` files (different concern — tests have their own time-handling)
- `time_utils.py` itself (the helpers being defined)
- `workflow_versioning.py` (legacy producer, intentionally retained per [#5169](https://github.com/mrveiss/AutoBot-AI/issues/5169) ADR until step 4 of the migration plan)

Counted on commit `352c43b9e` (Dev_new_gui head at audit time).

## Distribution by subsystem

| Subsystem | Files | Notes |
|---|---|---|
| `api/` | 18 | response timestamps, analytics records, KB record fields |
| `services/` | 15 | analytics, feedback, secrets, telemetry — mix of producers and stored records |
| `security/enterprise/` | 7 | compliance, SSO, threat detection records |
| `knowledge/` | 4 | metadata, audit log, versioning |
| `utils/` | 3 | response builders, chat utils |
| `agents/` | 3 | task pattern records |
| `autobot_memory_graph/` | 2 | session, secrets |
| `models/` | 1 | session_collaboration |
| `planner/` | 1 | task lifecycle |
| `websocket/` | 1 | presence |
| `judges/` | 1 | task outcome |
| `tests/` (excluded but present) | 1 | `tests/api/test_analytics_stratified.py` |

## The bug class — why this matters

`datetime.utcnow()` returns a **tz-naive** datetime. Calling `.isoformat()` produces a string with **no timezone suffix**:

```
>>> datetime.utcnow().isoformat()
'2026-04-19T17:04:53.711121'         ← no +00:00, no Z, naive
```

Compare to `utc_timestamp()`:

```
>>> from autobot_shared.time_utils import utc_timestamp
>>> utc_timestamp()
'2026-04-19T17:04:53.711121+00:00'   ← +00:00, tz-aware
```

**Consumer-side consequences** (cross-referencing the [parsing audit](datetime-parsing-audit.md)):

1. **All 55 unguarded `fromisoformat` parsers** receive a tz-naive datetime back from these timestamps — they then mis-compare against tz-aware datetimes (`TypeError: can't compare offset-naive and offset-aware datetimes`) the moment any consumer mixes the two.
2. The 9 Z-shim parsers ARE accidentally tolerant — they handle `Z`, `+00:00`, AND naive (the shim is a no-op on naive input, then `fromisoformat` accepts it).
3. **Python 3.14 deprecates `datetime.utcnow()`** — running tests on Py 3.12 will surface DeprecationWarnings everywhere this pattern appears. This audit's migration unblocks that upgrade.

## The 3 outliers

### 1. `conversation_export.py:69, 86` (2 sites) — careful migration

```python
"exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
```

Functionally correct (UTC, `Z` suffix). Used in conversation export records that are likely consumed by external tools / downloaded by users. Migrating to `utc_timestamp()` would change the format from `Z` second-precision to `+00:00` microsecond-precision — potentially breaking external consumers.

**Recommendation**: keep these as-is during Part B's mechanical migration. Address them during the `utc_timestamp_z()` deprecation path in #5169's step 4.

### 2. `man_page_knowledge_integrator.py:96` — REAL BUG

```python
last_updated=time.strftime("%Y-%m-%dT%H:%M:%S"),
```

`time.strftime` with no `time` argument uses **`time.localtime()`** by default — this is local time, naive, mislabeled as UTC by callers reading the `last_updated` field. **Pure bug**. Migrate this to `utc_timestamp()` in Part B without ceremony.

## Migration recommendation (Part B)

### Mechanical replacement (136 sites, 56 files)

```python
# before
"timestamp": datetime.utcnow().isoformat(),
# after
from autobot_shared.time_utils import utc_timestamp
"timestamp": utc_timestamp(),
```

A `sed` could do this safely (the pattern is unambiguous), but **an agent-driven migration with per-file `import` deduplication is cleaner** — many files use other `datetime` features that the import shouldn't break.

### Sequencing

| Phase | Files | Why first/last |
|---|---|---|
| **Phase 1** — `utils/`, `agents/`, `judges/`, `websocket/`, `models/`, `planner/`, `autobot_memory_graph/` (12 files) | low blast radius, internal consumers only | first — proves migration pattern |
| **Phase 2** — `services/`, `knowledge/` (19 files) | internal consumers, larger surface area | second — established pattern, batch through |
| **Phase 3** — `api/`, `security/enterprise/` (25 files) | external consumers (API responses, compliance records) | last — review-heavy; some response timestamps may need to retain naive form for API contract reasons |
| **Outliers** | `conversation_export.py` × 2, `man_page_knowledge_integrator.py` × 1 | handled per Outliers section above |

### Migration risk per phase

- **Phase 1-2**: low. Internal records, no external consumers. Behavior change: timestamps gain `+00:00` suffix (was: naive); any unguarded `fromisoformat` parser becomes correct (was: silently broken cross-comparison). Worst case: a dormant naive-vs-aware comparison surfaces and needs a one-line `.replace(tzinfo=timezone.utc)` patch.
- **Phase 3**: medium. API response timestamps are consumed by frontend + external clients — adding `+00:00` is technically a breaking change to the response shape. Most JSON parsers handle both, but worth a frontend smoke test.

## Lint enforcement (Part C of #5178)

After Phase 3 lands, add to `setup.cfg` / `pyproject.toml`:

```
flake8 / ruff:
  per-file-ignores: autobot_shared/time_utils.py,**/*workflow_versioning*
  rules:
    forbid-import-name = datetime.utcnow
    forbid-call = datetime.now() (when no args — flag for review)
```

Implementation detail: a custom flake8 plugin or a pre-commit `grep` hook is sufficient. The point is to prevent regression after the mass migration lands.

## Acceptance criteria covered

- [x] **Part A — Audit doc with 57-file breakdown** ← this document
- [x] Per-file Producer/Display/Test classification — every site is a Producer (the 1 test was excluded by the grep filter; the rest produce timestamps stored or returned)
- [ ] **Part B — Migration of all Producer-classified sites** — gated on this audit landing
- [ ] **Part C — Lint rule** — gated on Part B completion

## Next steps

- This PR ships Part A only — issue #5178 stays OPEN
- Part B can start immediately (canonicalization decision in #5169 unblocks it)
- Recommended split: 3 sub-PRs by Phase 1 / 2 / 3 above to keep review surface manageable

## Appendix — full file list

```
autobot-backend/agents/man_page_knowledge_integrator.py     (outlier — strftime bug)
autobot-backend/agents/task_pattern_learner.py
autobot-backend/agents/task_retry_strategy.py
autobot-backend/api/agent.py
autobot-backend/api/ai_stack_integration.py
autobot-backend/api/analytics_behavior.py
autobot-backend/api/analytics_cost.py
autobot-backend/api/analytics_export.py
autobot-backend/api/analytics_maintenance.py
autobot-backend/api/analytics_reporting.py
autobot-backend/api/captcha.py
autobot-backend/api/chat.py
autobot-backend/api/entity_extraction.py
autobot-backend/api/graph_rag.py
autobot-backend/api/knowledge_ai_stack.py
autobot-backend/api/knowledge_vectorization.py
autobot-backend/api/memory.py
autobot-backend/api/npu_workers.py
autobot-backend/api/phases.py
autobot-backend/api/project.py
autobot-backend/api/usage.py
autobot-backend/autobot_memory_graph/secrets.py
autobot-backend/autobot_memory_graph/user_session.py
autobot-backend/judges/task_outcome_judge.py
autobot-backend/knowledge/audit_log.py
autobot-backend/knowledge/metadata.py
autobot-backend/knowledge/pipeline/loaders/sqlite_loader.py
autobot-backend/knowledge/versioning.py
autobot-backend/models/session_collaboration.py
autobot-backend/planner/planner.py
autobot-backend/security/enterprise/compliance_manager.py
autobot-backend/security/enterprise/security_policy_manager.py
autobot-backend/security/enterprise/sso_integration.py
autobot-backend/security/enterprise/threat_detection/engine.py
autobot-backend/security/enterprise/threat_detection/learner.py
autobot-backend/security/enterprise/threat_detection/models.py
autobot-backend/security/enterprise/threat_detection/test_learner.py
autobot-backend/services/agent_analytics.py
autobot-backend/services/ai_stack_client.py
autobot-backend/services/analytics_service.py
autobot-backend/services/captcha_human_loop.py
autobot-backend/services/conversation_export.py                (outlier — Z export format)
autobot-backend/services/execution/modal_backend.py
autobot-backend/services/feedback_tracker.py
autobot-backend/services/incremental_trainer.py
autobot-backend/services/llm_cost_tracker.py
autobot-backend/services/nl_database_service.py
autobot-backend/services/npu_worker_manager.py
autobot-backend/services/saved_reports_service.py
autobot-backend/services/user_behavior_analytics.py
autobot-backend/services/workflow_serializer.py
autobot-backend/services/workflow_sharing_service.py
autobot-backend/tests/api/test_analytics_stratified.py        (excluded — test)
autobot-backend/utils/api_responses.py
autobot-backend/utils/chat_utils.py
autobot-backend/utils/response_helpers.py
autobot-backend/websocket/presence.py
```
