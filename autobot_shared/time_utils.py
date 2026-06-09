# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
3. ✅ Migrated 57 direct ``datetime.utcnow().isoformat()`` sites
   to ``utc_timestamp()`` — tracked by #5178
4. ⏳ Migrate ``workflow_versioning._utc_now`` → ``utc_timestamp``
   (after step 3, requires either tolerant readers or one-time
   data migration of stored Z records)
5. ✅ Deleted ``utc_timestamp_z()`` (after step 4)
6. ⏳ Python 3.11+ upgrade — drops the 9 ``.replace("Z", "+00:00")``
   workaround sites since 3.11 ``fromisoformat`` accepts ``Z`` natively
"""

from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return current UTC time as ISO-8601 with ``+00:00`` offset.

    Format: ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00`` (microsecond precision).
    Default helper for new code — see module docstring for selection rule.
    """
    return datetime.now(timezone.utc).isoformat()


def now_utc() -> datetime:
    """Return current UTC time as a tz-aware ``datetime``.

    Companion to :func:`utc_timestamp` for callers that need the
    ``datetime`` object itself (e.g. dataclass / Pydantic
    ``default_factory=``, ORM column ``default=``, arithmetic with
    ``timedelta``) rather than the ISO-8601 string.

    Equivalent to ``datetime.now(timezone.utc)`` but importable as a
    module-level callable so dataclass / Pydantic field defaults can
    pass it directly without a lambda::

        timestamp: datetime = field(default_factory=now_utc)
        # vs
        timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    Replaces ``datetime.utcnow`` (which Python 3.12 deprecates and
    which returns a tz-NAIVE datetime that mis-compares against
    tz-aware values) — see #5211 audit at
    ``docs/developer/audits/datetime-utcnow-non-isoformat-audit.md``.
    """
    return datetime.now(timezone.utc)


def parse_utc_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string and return a tz-aware UTC datetime.

    Accepts three forms:
    - ``+00:00`` offset (canonical, produced by :func:`utc_timestamp`)
    - ``Z`` suffix (legacy, produced by :func:`utc_timestamp_z`)
    - **Naive** (no offset/suffix) — assumed UTC and tagged as such

    Use this in consumer code that compares parsed timestamps against
    aware ``datetime`` values (e.g. ``cutoff = now_utc() - timedelta(...)``)
    when the input string may originate from external sources or legacy
    producers. Avoids the ``TypeError: can't compare offset-naive and
    offset-aware datetimes`` class flagged in #5350.

    Raises ``ValueError`` on non-string or malformed input — matches the
    ``datetime.fromisoformat`` exception surface adopters expect (#5464).
    Non-string inputs previously escaped as ``AttributeError`` from the
    inner ``.replace()`` call, slipping past the common
    ``except (ValueError, TypeError)`` adopter pattern.
    """
    if not isinstance(value, str):
        raise ValueError(f"parse_utc_iso: expected str, got {type(value).__name__}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
