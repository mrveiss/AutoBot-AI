"""Shared UTC timestamp helpers.

This module exposes two helpers for producing the current UTC time as an
ISO-8601 string. They differ in *output format*; the choice between them
is dictated by what consumers can parse, not by author preference.

Selection rule (#5106, #5152, #5169)
------------------------------------

``utc_timestamp()`` — **default for new code.**
    Returns ``+00:00`` ISO-8601 with microseconds
    (e.g. ``2026-04-18T19:34:50.123456+00:00``). Use this unless you are
    reading or writing a stored format that explicitly expects ``Z``.

``utc_timestamp_z()`` — **legacy compatibility only.**
    Returns ``Z``-suffix ISO-8601 with second precision and no
    microseconds (e.g. ``2026-04-18T19:34:50Z``). Use ONLY when reading
    or writing existing on-disk records that already use this format
    (currently: workflow-version records via
    ``services/workflow_versioning.py``). **Do not use for new
    producers** — pick ``utc_timestamp()`` instead so the codebase
    converges on one canonical format.

Long-term canonicalization (#5169 parts B + C) is deferred pending a
parser audit; until then both formats coexist and the rule above tells
new code which to pick.
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
    """Return current UTC time as ISO-8601 with ``Z`` suffix.

    Format: ``YYYY-MM-DDTHH:MM:SSZ`` (exactly 20 chars, second precision,
    no microseconds, no ``+00:00`` offset). Matches the on-disk format
    used by workflow_versioning records.

    Use ONLY for legacy compatibility — see module docstring for
    selection rule. Picking this for new producers perpetuates format
    drift (#5106, #5152, #5169).
    """
    t = time.gmtime()
    return (
        f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T"
        f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}Z"
    )
