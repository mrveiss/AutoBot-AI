# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Apply the retention table to the audit trail (#17225 D5).

The single purge path. ``tasks/audit_log_retention.py`` (nightly) and
``AuditLogger.cleanup_old_logs`` (the admin endpoint, which requires an
explicit confirmation) both call :func:`purge_expired`; neither scans keys of
its own. Each category is purged at its own period from ``retention.py``;
``cap_days`` (the operator's ``AUTOBOT_AUDIT_RETENTION_DAYS``, or the admin
endpoint's ``days_to_keep``) only ever shortens a period, never lengthens one.
"""

import json
from dataclasses import dataclass
from typing import Any, List

from autobot_shared.logging_manager import get_logger
from services.audit.projection import UNIFIED_KEY, category_key
from services.audit.retention import RETENTION_DAYS, cutoff_ts
from services.audit.taxonomy import AuditCategory

logger = get_logger(__name__)

#: Members of the unified key examined per purge run; the next run continues.
_UNIFIED_SCAN_LIMIT = 10_000


@dataclass
class PurgeResult:
    """What a purge removed (or, on a dry run, would remove)."""

    deleted: int = 0
    errors: int = 0


def _days(category: AuditCategory, cap_days: int | None) -> int:
    """The category's period from the table, never longer than *cap_days* when given."""
    policy = RETENTION_DAYS[category]
    return min(policy, cap_days) if cap_days else policy


async def _purge_category(redis: Any, category: AuditCategory, cutoff: float, dry_run: bool) -> int:
    key = category_key(category)
    if dry_run:
        return int(await redis.zcount(key, "-inf", cutoff))
    return int(await redis.zremrangebyscore(key, "-inf", cutoff))


def _expired_mixed_category_members(raws: List[Any], cap_days: int | None, now: float) -> List[Any]:
    expired = []
    for raw in raws:
        try:
            ev = json.loads(raw)
            category = AuditCategory(ev["category"])
        except (TypeError, ValueError, KeyError):
            continue
        if ev.get("occurred_at", 0) < cutoff_ts(_days(category, cap_days), now):
            expired.append(raw)
    return expired


async def _purge_all_category_key(redis: Any, cap_days: int | None, now: float, dry_run: bool) -> int:
    """The unified key mixes categories, so each member is judged by its own category."""
    shortest = min(_days(c, cap_days) for c in AuditCategory)
    raws = await redis.zrangebyscore(UNIFIED_KEY, "-inf", cutoff_ts(shortest, now), start=0, num=_UNIFIED_SCAN_LIMIT)
    expired = _expired_mixed_category_members(raws, cap_days, now)
    if expired and not dry_run:
        await redis.zrem(UNIFIED_KEY, *expired)
    return len(expired)


async def purge_expired(redis: Any, now: float, cap_days: int | None = None, dry_run: bool = False) -> PurgeResult:
    """Remove every audit record older than its retention period from the projection."""
    result = PurgeResult()
    for category in AuditCategory:
        try:
            result.deleted += await _purge_category(redis, category, cutoff_ts(_days(category, cap_days), now), dry_run)
        except Exception as exc:  # noqa: BLE001 -- one bad key must not stop the others
            result.errors += 1
            logger.error("Audit purge failed for %s: %s", category.value, type(exc).__name__)
    try:
        result.deleted += await _purge_all_category_key(redis, cap_days, now, dry_run)
    except Exception as exc:  # noqa: BLE001
        result.errors += 1
        logger.error("Audit purge failed for the unified key: %s", type(exc).__name__)
    return result
