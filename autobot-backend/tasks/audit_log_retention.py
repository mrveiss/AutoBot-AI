# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery beat task: audit log retention cleanup (GH#8995, #17225 D5).

Applies the one audit retention table (``services/audit/retention.py``) through
the one purge path (``services.audit.audit.apply_retention``). Each category is
purged at its own period; ``AUTOBOT_AUDIT_RETENTION_DAYS`` only ever shortens it.

Before #17225 this task scanned every ``audit:*`` key and trimmed each sorted set
at one period, so a 90-day setting also cut the 365-day KNOWLEDGE and GOVERNANCE
records, and it reached whatever other module shared the prefix.

Safe defaults: period=0 → task is a no-op.  Nothing is deleted unless
AUTOBOT_AUDIT_RETENTION_DAYS is set to a positive integer.
"""

from typing import Any, Dict

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config
from celery_app import celery_app
from services.audit.audit import AuditCategory, AuditEvent, apply_retention
from services.audit.audit import emit as audit_emit

logger = get_logger(__name__)

# Module-level constant — reads env at import time (cache.py pattern)
_AUDIT_RETENTION_DAYS = ssot_config.audit_retention_days


def _emit_purge_audit(deleted_logs: int, retention_days: int) -> None:
    """Emit a single audit event summarising the purge run."""
    audit_emit(
        AuditEvent(
            category=AuditCategory.SECURITY,
            action="audit_log_retention_purge",
            actor_id="system:retention_worker",
            resource_type="audit_log",
            metadata={"deleted_logs": deleted_logs, "retention_days": retention_days},
        )
    )


async def _async_cleanup_expired_audit_logs(retention_days: int, dry_run: bool = False) -> Dict[str, Any]:
    """Purge audit records past their category's period, capped at *retention_days*.

    Idempotent: a record already purged or expired is simply not found again.
    """
    if retention_days <= 0:
        logger.info("Audit log retention disabled (retention_days=%d), skipping.", retention_days)
        return {"deleted_logs": 0, "errors": 0}

    result = await apply_retention(cap_days=retention_days, dry_run=dry_run)
    if result.deleted and not dry_run:
        _emit_purge_audit(result.deleted, retention_days)

    logger.info(
        "Audit log retention: deleted_logs=%d errors=%d retention_days=%d dry_run=%s",
        result.deleted,
        result.errors,
        retention_days,
        dry_run,
    )
    return {"deleted_logs": result.deleted, "errors": result.errors}


@celery_app.task(bind=True, name="tasks.cleanup_expired_audit_logs")
def cleanup_expired_audit_logs(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove audit log entries past their retention (GH#8995, #17225 D5).

    retention_days defaults to AUTOBOT_AUDIT_RETENTION_DAYS (0 = disabled) and caps
    each category's period from the retention table.
    dry_run=True logs what would be deleted without making changes.
    """
    if retention_days is None:
        retention_days = _AUDIT_RETENTION_DAYS
    return run_or_schedule(_async_cleanup_expired_audit_logs(retention_days, dry_run))
