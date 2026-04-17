"""Shared time utility helpers."""
from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return the current time as an ISO-8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()
