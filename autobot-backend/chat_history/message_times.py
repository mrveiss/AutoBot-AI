# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The timestamp a persisted chat message carries (#21846).

It used to be local wall time in whole seconds (``%Y-%m-%d %H:%M:%S``): no zone, so a reader in another zone
(the browser) mis-read it by the offset, and steps inside one second were indistinguishable. A persisted message
now carries an ISO-8601 instant with microseconds and a ``+00:00`` offset, the form ``autobot_shared.time_utils``
already names the default for new code. Messages stored before this keep the old text; ``parse_message_timestamp``
reads both, reading an old one as the server's local time (which is what it recorded).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from autobot_shared.time_utils import parse_utc_iso, utc_timestamp

#: The gap that separates two messages persisted at the same instant (one microsecond: the stored resolution).
TIE_BREAK = timedelta(microseconds=1)


def message_timestamp(created_at: float | None = None) -> str:
    """The stored timestamp for a message created at *created_at* (epoch seconds), or now when None."""
    if created_at is None:
        return utc_timestamp()
    return datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()


def parse_message_timestamp(value: Any) -> datetime | None:
    """A stored message timestamp as a timezone-aware datetime; None when it is empty or unreadable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        if "T" in value:
            return parse_utc_iso(value)
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").astimezone()  # legacy: server-local wall time
    except (ValueError, TypeError):
        return None


def timestamp_sort_key(message: Dict[str, Any]) -> float:
    """Epoch seconds to order a message by: the old and the new format sort together; unreadable sorts first."""
    parsed = parse_message_timestamp(message.get("timestamp"))
    return parsed.timestamp() if parsed else float("-inf")


def distinct_ordered_times(messages: List[Dict[str, Any]]) -> None:
    """Give messages that share an instant distinct times, in list order (in place).

    A batch persisted at one instant (every entry built from the same clock reading) would otherwise store equal
    timestamps, so a reload could not order the steps. Only a tie is moved, one microsecond past the one before it;
    a message with its own earlier or later real time keeps it.
    """
    run_start: datetime | None = None  # the shared instant of the run of ties being spread
    last_given: datetime | None = None  # the latest time handed out inside that run
    for message in messages:
        parsed = parse_message_timestamp(message.get("timestamp"))
        if parsed is None:
            continue
        if run_start is not None and parsed == run_start and last_given is not None:
            last_given = last_given + TIE_BREAK
            message["timestamp"] = last_given.astimezone(timezone.utc).isoformat()
        else:
            run_start = last_given = parsed
