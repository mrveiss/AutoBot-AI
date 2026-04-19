"""Shared UTC timestamp helpers.

Canonical format (#5169): **`+00:00` ISO-8601 produced by `utc_timestamp()`.**

The parser audit at `docs/developer/audits/datetime-parsing-audit.md`
established that 86% of internal `fromisoformat` callers (55 of 64
files) are unguarded against `Z`-suffix input — they parse only the
`+00:00` form. Python 3.10's `fromisoformat` raises `ValueError` on
`Z`-suffix input. Aligning new producers with what the codebase
already parses is the safe direction.

Selection rule
--------------

``utc_timestamp()`` — **default. Use for all new code.**
    Returns ``+00:00`` ISO-8601 with microseconds
    (e.g. ``2026-04-18T19:34:50.123456+00:00``).
    Round-trips via ``datetime.fromisoformat`` on Python 3.10+.

``utc_timestamp_z()`` — **DEPRECATED — legacy compatibility only.**
    Returns ``Z``-suffix ISO-8601 with second precision
    (e.g. ``2026-04-18T19:34:50Z``). Retained ONLY because
    ``services/workflow_versioning.py`` writes records in this format
    historically. The audit confirmed zero internal parsers consume
    those records, so a future migration of that producer is safe and
    will allow this helper to be deleted.
    **Do not call from new code.**

Migration plan (#5169 part C)
-----------------------------

1. ✅ Selection rule documented (PR #5176)
2. ✅ Audit + canonicalization decision (this PR)
3. ⏳ Migrate 57 direct ``datetime.utcnow().isoformat()`` sites
   to ``utc_timestamp()`` — tracked by #5178
4. ⏳ Migrate ``workflow_versioning._utc_now`` → ``utc_timestamp``
   (after step 3, requires either tolerant readers or one-time
   data migration of stored Z records)
5. ⏳ Delete ``utc_timestamp_z()`` (after step 4)
6. ⏳ Python 3.11+ upgrade — drops the 9 ``.replace("Z", "+00:00")``
   workaround sites since 3.11 ``fromisoformat`` accepts ``Z`` natively
"""
import time
from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return current UTC time as ISO-8601 with ``+00:00`` offset.

    Format: ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00`` (microsecond precision).
    Default helper for new code — see module docstring for selection rule.
    """
    return datetime.now(timezone.utc).isoformat()


def utc_timestamp_z() -> str:
    """Return current UTC time as ISO-8601 with ``Z`` suffix. **DEPRECATED.**

    Format: ``YYYY-MM-DDTHH:MM:SSZ`` (exactly 20 chars, second precision,
    no microseconds, no ``+00:00`` offset). Matches the on-disk format
    used by ``services/workflow_versioning.py`` records.

    .. deprecated::
        Use :func:`utc_timestamp` for all new code. This helper is
        retained only for the single legacy producer above; see module
        docstring for the migration plan that will delete it (#5169).
        Calling this from new code violates the canonicalization
        decision and will be flagged in review.
    """
    t = time.gmtime()
    return (
        f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T"
        f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}Z"
    )
