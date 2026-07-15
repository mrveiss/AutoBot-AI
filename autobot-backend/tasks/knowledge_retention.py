# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery beat task: knowledge-base entry retention cleanup (GH#8995).

Removes KB facts (Redis ``fact:*`` hashes) older than the configured TTL.
Delegates actual deletion to KnowledgeBase.delete_fact so all vector/BM25
index side-effects are applied correctly.

Safe defaults: period=0 → task is a no-op.  Nothing is deleted unless
AUTOBOT_KB_RETENTION_DAYS is set to a positive integer.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config
from celery_app import celery_app
from services.audit.audit import AuditCategory, AuditEvent
from services.audit.audit import emit as audit_emit

logger = get_logger(__name__)

# Module-level constant — reads env at import time (cache.py pattern)
_KB_RETENTION_DAYS = ssot_config.kb_retention_days

_FACT_PATTERN = "fact:*"


def _emit_deletion_audit(fact_id: str, extra: Dict[str, Any]) -> None:
    """Fire-and-forget audit event for a KB retention deletion."""
    audit_emit(
        AuditEvent(
            category=AuditCategory.KNOWLEDGE,
            action="retention_purge",
            actor_id="system:retention_worker",
            resource_type="kb_entry",
            resource_id=fact_id,
            metadata=extra,
        )
    )


async def _async_cleanup_expired_kb_entries(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Remove KB facts older than retention_days.

    Uses KnowledgeBase.delete_fact so vector index side-effects are applied.
    Idempotent: facts already deleted are silently skipped.
    """
    if retention_days <= 0:
        logger.info("KB retention disabled (retention_days=%d), skipping.", retention_days)
        return {"deleted_entries": 0, "skipped": 0, "errors": 0}

    from autobot_shared.redis_client import get_redis_client
    from knowledge import get_knowledge_base

    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis client unavailable — skipping KB retention cleanup.")
        return {"deleted_entries": 0, "skipped": 0, "errors": 0}

    # Compute cutoff as ISO timestamp string for comparison
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    deleted_entries = 0
    skipped = 0
    errors = 0

    # Collect candidate fact IDs first (avoid mutating while scanning)
    candidates = []
    cursor: int = 0
    while True:
        cursor, keys = redis_client.scan(cursor, match=_FACT_PATTERN, count=200)
        for key in keys:
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            # Only process bare fact:<id> hashes, not index/mapping keys
            parts = key_str.split(":")
            if len(parts) != 2:
                continue
            fact_id = parts[1]
            try:
                raw_ts = redis_client.hget(key, "timestamp")
                if not raw_ts:
                    skipped += 1
                    continue
                ts_str = raw_ts.decode("utf-8") if isinstance(raw_ts, bytes) else raw_ts
                fact_ts = datetime.fromisoformat(ts_str)
                if fact_ts.tzinfo is None:
                    fact_ts = fact_ts.replace(tzinfo=timezone.utc)
                if fact_ts >= cutoff:
                    continue
                age_days = (datetime.now(timezone.utc) - fact_ts).days
                candidates.append((fact_id, age_days))
            except Exception as exc:
                skipped += 1
                logger.debug("Skipping %s — cannot parse timestamp: %s", key_str, exc)
        if cursor == 0:
            break

    if not candidates:
        logger.info("KB retention: no entries older than %d days found.", retention_days)
        return {"deleted_entries": 0, "skipped": skipped, "errors": 0}

    kb = await get_knowledge_base()

    for fact_id, age_days in candidates:
        try:
            if dry_run:
                logger.info("[DRY RUN] Would delete KB fact %s (age=%dd)", fact_id, age_days)
                deleted_entries += 1
            else:
                result = await kb.delete_fact(fact_id, _skip_bm25_refresh=True)
                if result.get("status") == "success":
                    _emit_deletion_audit(fact_id, {"age_days": age_days, "retention_days": retention_days})
                    deleted_entries += 1
                    logger.debug("Deleted KB fact %s (age=%dd)", fact_id, age_days)
                else:
                    # Already deleted or not found — idempotent
                    skipped += 1
        except Exception as exc:
            errors += 1
            logger.error("Error deleting KB fact %s: %s", fact_id, exc)

    # Trigger BM25 refresh once after bulk delete
    if deleted_entries and not dry_run:
        try:
            kb._schedule_bm25_refresh()
        except Exception:
            pass

    logger.info(
        "KB retention: deleted_entries=%d skipped=%d errors=%d retention_days=%d dry_run=%s",
        deleted_entries,
        skipped,
        errors,
        retention_days,
        dry_run,
    )
    return {"deleted_entries": deleted_entries, "skipped": skipped, "errors": errors}


@celery_app.task(bind=True, name="tasks.cleanup_expired_kb_entries")
def cleanup_expired_kb_entries(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove knowledge-base entries older than retention_days (GH#8995).

    retention_days defaults to AUTOBOT_KB_RETENTION_DAYS (0 = disabled).
    dry_run=True logs what would be deleted without making changes.
    """
    if retention_days is None:
        retention_days = _KB_RETENTION_DAYS
    return run_or_schedule(_async_cleanup_expired_kb_entries(retention_days, dry_run))
