# Datetime Parsing Audit — `fromisoformat` and `strptime` Tolerance

> **Status**: Part B + Part C of [#5169](https://github.com/mrveiss/AutoBot-AI/issues/5169). Closes the issue.
> **Scope**: backend Python parsers of UTC-ISO-8601 strings. Frontend / TS parsers out of scope.
> **Output**: parser landscape evidence + canonicalization decision.

## TL;DR

| Format | Producer | Python 3.10 `fromisoformat` | Internal consumer count |
|---|---|---|---|
| `2026-04-18T19:34:50.123456+00:00` | `utc_timestamp()` | ✅ accepts | 64 files |
| `2026-04-18T19:34:50Z` | `utc_timestamp_z()` | ❌ **raises `ValueError`** | 0 files (write-only producer) |
| `2026-04-18T19:34:50` (naive) | `datetime.utcnow().isoformat()` | ✅ accepts (returns naive) | tracked separately by [#5178](https://github.com/mrveiss/AutoBot-AI/issues/5178) |

**Decision (Part C)**: canonicalize on `+00:00`. Mark `utc_timestamp_z()` deprecated. Plan a Python 3.11 upgrade so the 9 explicit Z-shim sites become redundant. **Resolved (#13755):** the platform runs 3.14, `utc_timestamp_z()` is deleted, and all Z-shim sites are gone. No on-disk data migration required — the only Z-suffix producer (`workflow_versioning`) has zero internal parsers.

---

## Part B — Parser landscape

### Method

```bash
grep -rn "fromisoformat" autobot-backend autobot_shared --include="*.py" | grep -v "_test.py\|__pycache__"
grep -rn "strptime"      autobot-backend autobot_shared --include="*.py" | grep -v "_test.py\|__pycache__"
```

### Counts

- **`fromisoformat` callers**: 64 files (119 call sites)
- **Files with explicit `Z`-shim** (`replace("Z", "+00:00")` / `rstrip("Z")`): **9** (~14%)
- **`strptime` callers**: 13 sites — none parse ISO-8601 with timezone suffix; all use SQLite TEXT (`%Y-%m-%d %H:%M:%S`), date-only (`%Y-%m-%d`), hour bucket, or PKI cert format. **Irrelevant to ISO-8601 canonicalization.**

### Distribution by subsystem

```
api/         18 files   ← largest cluster (response normalization, analytics)
knowledge/    9 files   ← KB metadata, connectors
services/     8 files   ← agent_analytics, feedback_tracker, secrets
security/     6 files
utils/        4 files
models/       4 files
memory/       2 files
code_intel/   2 files
tests/        3 files
```

### Tolerance classification

#### Class A — Z-shim guarded (handles both `Z` and `+00:00`)

9 files. Pattern: `datetime.fromisoformat(s.replace("Z", "+00:00"))` or `.rstrip("Z")`.

| File | Line | Source of input |
|---|---|---|
| [`utils/branch_metrics.py:104`](autobot-backend/utils/branch_metrics.py) | 104 | git CLI output |
| [`chat_history/deduplication.py:29`](autobot-backend/chat_history/deduplication.py) | 29 | message timestamps |
| [`knowledge/metadata.py:423`](autobot-backend/knowledge/metadata.py) | 423 | KB metadata field |
| [`knowledge/connectors/notion.py:288`](autobot-backend/knowledge/connectors/notion.py) | 288 | Notion API response (Z-format) |
| [`api/knowledge_organization.py:333`](autobot-backend/api/knowledge_organization.py) | 333 | KB record field |
| [`api/analytics_evolution.py:980`](autobot-backend/api/analytics_evolution.py) | 980 | analytics record |
| [`api/analytics_conversation.py:40,52,495`](autobot-backend/api/analytics_conversation.py) | 40, 52, 495 | conversation record |
| [`api/chat.py:140`](autobot-backend/api/chat.py) | 140 | chat record |

**These 9 files are safe under either format.** The shim was defensive: it was added because external APIs (Notion, git, Redis writes from older AutoBot versions) sometimes emit `Z`. Both preconditions are now met, so the shim was removed in #13755 — external `Z` producers are still tolerated, by `fromisoformat` itself rather than by a preprocessing step. Six of the nine sites had already gone by other routes; the remaining three were removed together.

#### Class B — unguarded (assumes `+00:00` or naive)

55 files (86%). Pattern: `datetime.fromisoformat(s)` with no preprocessing.

Spot-check sample:

| File | Line | Field | Producer |
|---|---|---|---|
| [`project_state_tracking/database.py:260`](autobot-backend/project_state_tracking/database.py) | 260 | `row[0]` (SQLite TEXT) | internal write via `utc_timestamp()` or `datetime.utcnow().isoformat()` |
| [`memory/storage/general_storage.py:223`](autobot-backend/memory/storage/general_storage.py) | 223 | `row["timestamp"]` | internal write |
| [`memory/storage/task_storage.py:296,301,306`](autobot-backend/memory/storage/task_storage.py) | 296-306 | `created_at`, `started_at`, `completed_at` | internal write |
| [`planner/types.py:105,110,285,290`](autobot-backend/planner/types.py) | 105-290 | task lifecycle fields | internal write |
| [`events/types.py:157`](autobot-backend/events/types.py) | 157 | `data["timestamp"]` (event envelope) | internal write |

**Risk profile**: each unguarded site would raise `ValueError` on Python 3.10 if fed a `Z`-suffix string. They work today because the producers feeding them never emit `Z` (they use `utc_timestamp()` → `+00:00`, or `datetime.utcnow().isoformat()` → naive).

The 55 sites form an **invariant**: as long as no internal producer switches to `Z` form, no parser breaks. **`utc_timestamp_z()` violates this invariant**, but its output (`workflow_versioning` records) has zero internal parsers — so the violation is contained.

#### Class C — strict-format `strptime` (irrelevant)

All 13 sites parse non-ISO-8601 formats:

```
api/chat.py:141                      "%Y-%m-%d %H:%M:%S"      ← SQLite TEXT
chat_history/deduplication.py:30     "%Y-%m-%d %H:%M:%S"      ← SQLite TEXT
pki/generator.py:431                 "%b %d %H:%M:%S %Y %Z"   ← OpenSSL output
knowledge/bulk.py:49,77              "%Y-%m-%d"               ← date-only
knowledge/stats.py:796               "%Y-%m-%d"               ← date-only
api/knowledge_models.py:399,1723     "%Y-%m-%d"               ← date-only
api/analytics_log_patterns.py:171    "%Y-%m-%d %H:%M:%S"      ← log format
api/analytics_log_patterns.py:403,4  "%Y-%m-%d %H:00"         ← hour bucket
code_intelligence/log_pattern_miner.py:322,880  same as above
```

None of these would parse `utc_timestamp()` or `utc_timestamp_z()` output. They're orthogonal concerns and out of scope for the canonicalization decision.

### Workflow_versioning record consumers

Critical question: who parses the records produced by `_utc_now()` (now `utc_timestamp_z` after PR #5163)?

```bash
grep -rn "workflow_versioning\|WorkflowVersion\|workflow:version" autobot-backend --include="*.py" \
  | grep -v "_test.py\|__pycache__\|services/workflow_versioning.py"
# (zero hits)
```

**Zero internal consumers grep-found** outside of `workflow_versioning.py` itself. The records are written and either (a) returned verbatim to API clients (display-only) or (b) never re-read at all. Either way, the on-disk format choice has no parser dependency — we can change it whenever we want without breaking anything internal.

### Python version constraint

```
$ python3 --version
Python 3.10.12
```

`datetime.fromisoformat` does not accept `Z` suffix on Python 3.10:

```
>>> datetime.fromisoformat('2026-04-18T19:34:50Z')
ValueError: Invalid isoformat string: '2026-04-18T19:34:50Z'

>>> datetime.fromisoformat('2026-04-18T19:34:50+00:00')
datetime.datetime(2026, 4, 18, 19, 34, 50, tzinfo=datetime.timezone.utc)
```

This was changed in Python 3.11 — `fromisoformat` accepts both forms natively from then on.

---

## Part C — Canonicalization decision (ADR)

### Decision

**Canonicalize the AutoBot codebase on `+00:00` ISO-8601 (the format produced by `utc_timestamp()`).**

Rationale:
1. **No on-disk migration risk.** The only `Z`-format producer (`workflow_versioning`) has zero internal parsers. We can deprecate `utc_timestamp_z()` without touching any record.
2. **86% of parsers are already only-`+00:00`-compatible.** They work today because all our internal producers emit `+00:00` or naive. Choosing `+00:00` aligns the rule with what the codebase already does.
3. **The Z-shim was a workaround, not a feature.** 9 files preprocessed `Z`→`+00:00` defensively because external APIs (Notion, git, etc.) emit `Z`. The upgrade landed and the shim is gone (#13755). Designing internal producers around an external-API quirk is the wrong direction.
4. **`+00:00` is what `datetime.now(timezone.utc).isoformat()` produces by default.** Picking the Python idiomatic form means new code is correct without thinking about format.

### Implementation plan

| Step | Status | Owner |
|---|---|---|
| 1. Document selection rule (Part A) | ✅ Done — PR #5176 | — |
| 2. Mark `utc_timestamp_z()` as `@deprecated` in docstring | ✅ This PR | — |
| 3. Migrate 57 direct `datetime.utcnow().isoformat()` sites to `utc_timestamp()` | Tracked by [#5178](https://github.com/mrveiss/AutoBot-AI/issues/5178) | — |
| 4. Migrate `workflow_versioning._utc_now` consumer to `utc_timestamp()` | ✅ Done — imports it as `_utc_now` | — |
| 5. Delete `utc_timestamp_z()` from `time_utils.py` | ✅ Done | — |
| 6. Plan Python 3.11+ upgrade | ✅ Done — the platform runs 3.14, enforced at boot (#13738) | — |
| 7. Drop the 9 Z-shim workarounds (no longer needed after step 6) | ✅ Done — [#13755](https://github.com/mrveiss/AutoBot-AI/issues/13755) | — |

### What this PR does (closes #5169)

- ✅ This audit document (Part B)
- ✅ Decision recorded above (Part C)
- ✅ `utc_timestamp_z()` marked `@deprecated` in [`autobot_shared/time_utils.py`](../../../autobot_shared/time_utils.py) docstring with migration pointer

Steps 3–7 are tracked as separate issues (#5178 + future). #5169 itself is closed by this PR.

### What this PR does NOT do

- Does not migrate any of the 57 direct-usage sites — that's #5178
- Does not delete `utc_timestamp_z()` — premature; it's still the canonical alias for `workflow_versioning`'s on-disk format until step 4
- Does not bump Python to 3.11 — that's a separate scope
- Does not touch the 9 Z-shim sites — they remain defensive against external APIs even after canonicalization (removed later, in #13755, once the interpreter floor made them redundant)

---

## Appendix — full grep output

```
$ grep -rln "fromisoformat" autobot-backend autobot_shared --include="*.py" | grep -v "_test.py\|__pycache__" | wc -l
64

$ grep -rln "fromisoformat.*replace.*Z\|fromisoformat.*rstrip.*Z" autobot-backend autobot_shared --include="*.py" | grep -v "_test.py\|__pycache__" | wc -l
9

$ grep -rn "strptime" autobot-backend autobot_shared --include="*.py" | grep -v "_test.py\|__pycache__" | wc -l
13
```

Counts as of commit `b545e8326` (Dev_new_gui head at audit time).
