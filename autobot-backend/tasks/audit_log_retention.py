# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery beat task: audit log retention cleanup (GH#8995, MVA-3044).

Removes audit log entries older than the configured TTL to prevent
unbounded storage growth in long-running deployments.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from celery_app import celery_app

logger = get_logger(__name__)

_DEFAULT_AUDIT_RETENTION_DAYS = 365  # 1 year default for audit logs


async def _async_cleanup_expired_audit_logs(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Remove audit log entries older than retention_days (async helper for Celery task).

    Args:
        retention_days: Number of days to retain audit logs
        dry_run: If True, log what would be deleted without actually deleting

    Returns:
        Dict with "deleted_logs" and "errors" counts
    """
    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis client not available, skipping audit log retention cleanup")
        return {"deleted_logs": 0, "errors": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_timestamp = cutoff.timestamp()

    deleted_logs = 0
    errors = 0

    try:
        # Cleanup audit log sorted sets/keys
        # Pattern: audit:* (assumes audit logs use timestamp-based sorted sets)
        audit_pattern = "audit:*"
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=audit_pattern, count=100)
            for key in keys:
                try:
                    # Check if it's a sorted set (audit logs typically use zsets with timestamps)
                    key_type = redis_client.type(key)
                    if key_type == "zset":
                        # Remove entries with scores (timestamps) older than cutoff
                        if dry_run:
                            old_count = redis_client.zcount(key, "-inf", cutoff_timestamp)
                            if old_count > 0:
                                logger.info(
                                    "[DRY RUN] Would remove %d old entries from %s (older than %s)",
                                    old_count,
                                    key,
                                    cutoff.isoformat(),
                                )
                                deleted_logs += old_count
                        else:
                            removed = redis_client.zremrangebyscore(key, "-inf", cutoff_timestamp)
                            if removed > 0:
                                deleted_logs += removed
                                logger.info(
                                    "Removed %d old entries from %s (older than %s)",
                                    removed,
                                    key,
                                    cutoff.isoformat(),
                                )
                    elif key_type == "string":
                        # For string keys, check idle time
                        idle_time = redis_client.object("IDLETIME", key)
                        if idle_time is None:
                            continue

                        idle_days = idle_time / 86400
                        if idle_days > retention_days:
                            if dry_run:
                                logger.info("[DRY RUN] Would delete audit key: %s (idle: %.1f days)", key, idle_days)
                                deleted_logs += 1
                            else:
                                redis_client.delete(key)
                                deleted_logs += 1
                                logger.debug("Deleted audit key: %s (idle: %.1f days)", key, idle_days)

                except Exception as exc:
                    errors += 1
                    logger.error("Failed to process audit key %s: %s", key, exc)

            if cursor == 0:
                break

    except Exception as exc:
        errors += 1
        logger.error("Audit log retention cleanup failed: %s", exc)

    logger.info(
        "Audit log retention cleanup: deleted_logs=%d, errors=%d, retention_days=%d, dry_run=%s",
        deleted_logs,
        errors,
        retention_days,
        dry_run,
    )
    return {
        "deleted_logs": deleted_logs,
        "errors": errors,
    }


@celery_app.task(bind=True, name="tasks.cleanup_expired_audit_logs")
def cleanup_expired_audit_logs(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove audit log entries older than retention_days (GH#8995, MVA-3044).

    Args:
        retention_days: Number of days to retain audit logs. Defaults to
                        AUTOBOT_AUDIT_RETENTION_DAYS env var or 365 days.
        dry_run: If True, log what would be deleted without actually deleting.

    Returns:
        Dict with "deleted_logs" and "errors" counts.
    """
    if retention_days is None:
        retention_days = int(os.getenv("AUTOBOT_AUDIT_RETENTION_DAYS", _DEFAULT_AUDIT_RETENTION_DAYS))

    return run_or_schedule(_async_cleanup_expired_audit_logs(retention_days, dry_run))
