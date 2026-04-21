# Datetime Cutoff Consumer Audit (#5350)

> Companion to [datetime-parsing-audit.md](datetime-parsing-audit.md) and [datetime-utcnow-non-isoformat-audit.md](datetime-utcnow-non-isoformat-audit.md).

## Why this audit exists

PR [#5342](https://github.com/mrveiss/AutoBot-AI/pull/5342) (#5211 Phase B3.2) migrated 12 sites from
`cutoff = datetime.utcnow() - timedelta(...)` to `cutoff = now_utc() - timedelta(...)`.
The migrated variables are now **tz-aware**; before they were **naive**.

This shifts the bug class from *naive vs naive (silently wrong)* to
*aware vs naive (loud `TypeError`)*. The loud failures are good — they
expose latent bugs — but each one needs a proven-safe consumer trace
before merging.

[#5350](https://github.com/mrveiss/AutoBot-AI/issues/5350) tracked the per-site verification.
This document is the verification record.

## Verification table

| # | File / line | Migrated var | Consumer | Status |
|---|---|---|---|---|
| 1 | `services/feedback_tracker.py:152` | `cutoff` (then `.timestamp()`) | `redis.zremrangebyscore` (numeric) | ✅ epoch float — aware-ness invisible |
| 2 | `services/feedback_tracker.py:163` | `last_retrain` | DB query against `Column(DateTime(timezone=True))` | ✅ AWARE column |
| 3 | `services/feedback_tracker.py:251` | `since` | DB query against same column | ✅ AWARE column |
| 4 | `services/incremental_trainer.py:149` | `since` | DB query against same column | ✅ AWARE column |
| 5 | `api/usage.py:248` | `cutoff` | `cutoff.strftime("%Y-%m-%dT")` then string-prefix compare | ✅ string boundary — tz invisible |
| 6 | `api/knowledge_organization.py:386` | `cutoff_date` | `_delete_expired_facts()` parses stored ISO via `fromisoformat(s.replace("Z","+00:00"))` → aware | ✅ aware vs aware |
| 7 | `services/agent_analytics.py:639` | `cutoff` | `fromisoformat(t["started_at"])` — `started_at` is produced by `utc_timestamp()` (line 248) → `+00:00` aware | ✅ aware vs aware |
| 8 | `security/.../engine.py:649` | `cutoff_time` | `session_data.get("last_activity", datetime.utcnow())` ← **naive fallback** vs aware cutoff | 🔴 **fixed** — see Fix 1 |
| 9 | `security/.../learner.py:233` | `cutoff` | `fromisoformat(last_seen_raw)` — `last_seen` written via `utc_timestamp()` (line 88) → aware | ✅ aware vs aware |
| 10 | `security/.../models.py:143` | `cutoff_time` (count_recent_failures) | `fromisoformat(event["timestamp"])` — fallback aware, but public API (engine `analyze_event` docstring) accepts caller-provided string with no tz | ⚠️ **hardened** — see Fix 2 |
| 11 | `security/.../models.py:168` | `cutoff_time` (count_recent_api_requests) | same | ⚠️ **hardened** — see Fix 2 |
| 12 | `security/.../models.py:188` | `cutoff_time` (get_recent_action_frequency) | same | ⚠️ **hardened** — see Fix 2 |
| 13 | `security/.../models.py:206` | `cutoff_time` (get_recent_endpoint_usage) | same | ⚠️ **hardened** — see Fix 2 |

> Site count became 13 because issue #5350 listed `models.py:143,168,188,206` as one row. Each is a distinct comparison.

## Fix 1 — `engine.py` (real bug)

**File:** `autobot-backend/security/enterprise/threat_detection/engine.py`

```diff
-                if session_data.get("last_activity", datetime.utcnow()) < cutoff_time:
+                if session_data.get("last_activity", now_utc()) < cutoff_time:
```

Trigger: any session that lacks `last_activity` (any code path that
inserts a session without that key, or any newly-created session whose
first activity hasn't fired yet). On hit: `TypeError: can't compare
offset-naive and offset-aware datetimes`. The `try/except` at line 668
would swallow the error, drop the cleanup pass, and leave stale sessions
indefinitely — a slow leak, not a crash.

The same module also had:

```diff
-            if datetime.utcnow().hour == 0:  # Midnight
+            if now_utc().hour == 0:  # Midnight
```

Standalone `.hour` works on both naive and aware, so this is a consistency
fix not a bug — but consistent helpers prevent future copy-paste bugs.

## Fix 2 — `models.py` parsing hardening

The public engine entry point (`engine.analyze_event(event: Dict)`) had a
docstring example with naive `"timestamp": "2025-01-01T12:00:00"`. Five
parser sites consume that field via `datetime.fromisoformat(...)`:

- `SecurityEvent.timestamp` (property, line 53)
- `EventHistory.count_recent_failures` (line 147)
- `EventHistory.count_recent_api_requests` (line 172)
- `EventHistory.get_recent_action_frequency` (line 192)
- `EventHistory.get_recent_endpoint_usage` (line 210)

If a caller followed the docstring and passed a naive string, the result
parsed naive and then mis-compared against the aware `cutoff_time`.

### Helper added — `parse_utc_iso(s)`

`autobot_shared/time_utils.py`:

```python
def parse_utc_iso(value: str) -> datetime:
    """Parse ISO-8601 timestamp; return tz-aware UTC datetime.

    Accepts +00:00 offset, Z suffix, or naive (assumed UTC).
    Use in consumer code that compares parsed timestamps against
    aware values (e.g. cutoff = now_utc() - timedelta(...)).
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
```

Five tests added to `time_utils_test.py` cover canonical, Z-suffix,
naive, comparable-with-now_utc, and malformed input.

### Sites migrated

All 5 `datetime.fromisoformat(...)` sites in `models.py` switched to
`parse_utc_iso(...)`. The docstring example in `__init__.py` was also
updated to canonical `"2025-01-01T12:00:00+00:00"` so future copy-pasters
follow the right pattern.

## Fix 3 — `UserProfile.last_updated` (hidden bug)

While auditing models.py, found:

| Line | Code | tz |
|---|---|---|
| 285 | `last_updated: datetime = field(default_factory=now_utc)` | aware |
| 350 | `self.last_updated = datetime.utcnow()` | naive |
| 389 | `(datetime.utcnow() - self.last_updated).days` | naive arithmetic |

Default factory produces aware. First call to `update_with_event()`
overwrites with naive. Then `get_risk_assessment()` does
`naive - <aware-or-naive>` — `TypeError` if `update_with_event` hasn't
been called since instantiation but `get_risk_assessment` has.

Fix: both line 350 and 389 migrated to `now_utc()`. The whole field is
now consistently aware regardless of code path.

## Out-of-scope (deferred)

- `engine.py:621` parses `event["timestamp"]` only to read `.hour` for
  ML feature extraction. Naive vs aware is invisible to `.hour`. Not
  changed (would add a needless dependency on the new helper).
- `engine.py` and module-wide migration of remaining `datetime` symbol
  usage is out of scope; only the comparison-against-aware sites that
  were proven unsafe were touched.

## Impact summary

- **1 latent bug fixed** (engine.py:649 — silent cleanup-pass failure)
- **1 latent bug fixed** (models.py UserProfile mixed-aware-naive arithmetic)
- **5 parser sites hardened** (models.py — robust against naive
  caller-provided timestamps consistent with public API docstring)
- **1 helper added** (`parse_utc_iso`) + 5 unit tests
- **1 docstring corrected** (engine `__init__.py` — canonical example)
- **9 of 13 sites proven safe** without code changes (DB columns + epoch +
  string-prefix + producer-controlled internal fromisoformat)

## Verification command

```bash
python3 -m pytest autobot_shared/time_utils_test.py -q
# 17 passed (12 prior + 5 new)
```
