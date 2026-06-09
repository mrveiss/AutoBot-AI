# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical datetime helpers for timezone-aware UTC operations.

Re-exports and aliases from autobot_shared.time_utils with helper functions
for normalizing naive/aware datetimes to UTC.

See #7436 (GitHub) and MVA-48 (Paperclip) for the migration plan.
"""

from datetime import datetime, timezone

from autobot_shared.time_utils import now_utc, utc_timestamp

# Canonical aliases matching MVA-48 naming convention
datetime_now = now_utc
iso_utc = utc_timestamp


def to_utc(dt: datetime) -> datetime:
    """Normalize a naive or aware datetime to tz-aware UTC.

    Naive datetimes are assumed UTC and tagged as such.
    Aware datetimes in other zones are converted to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
