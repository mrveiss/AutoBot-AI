# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery beat task: audit log retention cleanup (GH#8995).

Prunes entries from Redis audit sorted-sets that are older than the
configured TTL.

Safe defaults: period=0 → task is a no-op.  Nothing is deleted unless
AUTOBOT_AUDIT_RETENTION_DAYS is set to a positive integer.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config as ssot_config
from celery_app import celery_app
from services.audit.unified_audit import AuditCategory, AuditEvent
from services.audit.unified_audit import emit as audit_emit

logger = get_logger(__name__)

# Module-level constant — reads env at import time (cache.py pattern)
_AUDIT_RETENTION_DAYS = ssot_config.audit_retention_days

_AUDIT_PATTERN = "audit:*"


def _emit_purge_audit(deleted_logs: int, retention_days: int, extra: Dict[str, Any]) -> None:
    """Emit a single audit event summarising the purge run."""
    audit_emit(
        AuditEvent(
            category=AuditCategory.SECURITY,
            action="audit_log_retention_purge",
            actor_id="system:retention_worker",
            resource_type="audit_log",
            metadata={"deleted_logs": deleted_logs, "retention_days": retention_days, **extra},
        )
    )


async def _async_cleanup_expired_audit_logs(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Remove audit log entries older than retention_days from Redis zsets.

    Idempotent: keys already expired/deleted are silently skipped.
    """
    if retention_days <= 0:
        logger.info("Audit log retention disabled (retention_days=%d), skipping.", retention_days)
        return {"deleted_logs": 0, "errors": 0}

    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis client unavailable — skipping audit log retention cleanup.")
        return {"deleted_logs": 0, "errors": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_ts = cutoff.timestamp()
    deleted_logs = 0
    errors = 0

    cursor: int = 0
    while True:
        cursor, keys = redis_client.scan(cursor, match=_AUDIT_PATTERN, count=200)
        for key in keys:
            try:
                key_type = redis_client.type(key)
                if key_type != "zset":
                    continue
                if dry_run:
                    count = redis_client.zcount(key, "-inf", cutoff_ts)
                    if count:
                        logger.info("[DRY RUN] Would remove %d entries from %s", count, key)
                        deleted_logs += count
                else:
                    removed = redis_client.zremrangebyscore(key, "-inf", cutoff_ts)
                    if removed:
                        deleted_logs += removed
                        logger.debug("Removed %d old entries from %s", removed, key)
            except Exception as exc:
                errors += 1
                logger.error("Error processing audit key %s: %s", key, exc)
        if cursor == 0:
            break

    if deleted_logs and not dry_run:
        _emit_purge_audit(deleted_logs, retention_days, {"cutoff_ts": cutoff_ts})

    logger.info(
        "Audit log retention: deleted_logs=%d errors=%d retention_days=%d dry_run=%s",
        deleted_logs,
        errors,
        retention_days,
        dry_run,
    )
    return {"deleted_logs": deleted_logs, "errors": errors}


@celery_app.task(bind=True, name="tasks.cleanup_expired_audit_logs")
def cleanup_expired_audit_logs(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove audit log entries older than retention_days (GH#8995).

    retention_days defaults to AUTOBOT_AUDIT_RETENTION_DAYS (0 = disabled).
    dry_run=True logs what would be deleted without making changes.
    """
    if retention_days is None:
        retention_days = _AUDIT_RETENTION_DAYS
    return run_or_schedule(_async_cleanup_expired_audit_logs(retention_days, dry_run))
