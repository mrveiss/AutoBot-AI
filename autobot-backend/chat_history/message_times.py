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

#: The least gap between two messages persisted together: one millisecond, the resolution of a browser ``Date``.
TIE_BREAK = timedelta(milliseconds=1)


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
    """Give messages persisted within one millisecond of each other distinct times, in list order (in place).

    A batch persisted at one instant (every entry built from the same clock reading) would otherwise store equal
    timestamps, so a reload could not order the steps. A browser ``Date`` holds milliseconds, so a gap under a
    millisecond is a tie to the frontend readers too: a message that is not at least ``TIE_BREAK`` after the one
    before it (and not earlier than it) is moved to exactly that gap. A message with an earlier or a clearly
    later real time keeps it.
    """
    last: datetime | None = None  # the time the previous message ended up with
    previous_own: datetime | None = None  # the time the previous message was built with
    for message in messages:
        own = parse_message_timestamp(message.get("timestamp"))
        if own is None:
            continue
        parsed = own
        if last is not None and previous_own is not None and previous_own <= own < last + TIE_BREAK:
            parsed = last + TIE_BREAK
            message["timestamp"] = parsed.astimezone(timezone.utc).isoformat()
        last, previous_own = parsed, own
