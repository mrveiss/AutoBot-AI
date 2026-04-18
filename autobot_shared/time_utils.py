"""Shared time utility helpers."""
import time
from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return the current time as an ISO-8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


def utc_timestamp_z() -> str:
    """Return current UTC time as an ISO-8601 string with Z suffix.

    Produces exactly 20 characters in the form ``YYYY-MM-DDTHH:MM:SSZ``
    with no microseconds and no ``+00:00`` offset — matching the on-disk
    format used by workflow_versioning records (#5152).
    """
    t = time.gmtime()
    return (
        f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T"
        f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}Z"
    )
