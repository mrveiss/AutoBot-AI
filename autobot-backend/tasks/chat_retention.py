# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery beat task: chat history retention cleanup (GH#8995).

Removes chat sessions older than the configured TTL.  Sessions with
``keep_forever=true`` in their stored JSON are always exempt.

Safe defaults: period=0 → task is a no-op.  Nothing is deleted unless
AUTOBOT_CHAT_RETENTION_DAYS is set to a positive integer.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config as ssot_config
from celery_app import celery_app
from services.audit.audit import AuditCategory, AuditEvent
from services.audit.audit import emit as audit_emit

logger = get_logger(__name__)

# Module-level constant — reads env at import time (cache.py pattern)
_CHAT_RETENTION_DAYS = ssot_config.chat_retention_days

# Redis sorted-set that maps session_id → last-update timestamp
_RECENT_KEY = "chat:recent"
# Prefix for individual session JSON blobs
_SESSION_PREFIX = "chat:session:"
_CONVERSATION_PREFIX = "chat:conversation:"


def _is_keep_forever(raw: bytes) -> bool:
    """Return True if the stored session JSON has keep_forever set."""
    try:
        data = json.loads(raw)
        return bool(data.get("keep_forever") or data.get("keepForever"))
    except Exception:
        return False


def _parse_created_at(raw: bytes) -> datetime | None:
    """Extract createdAt timestamp from stored session JSON.

    Returns a timezone-aware datetime or None when unavailable/unparseable.
    """
    try:
        data = json.loads(raw)
        raw_ts = data.get("createdAt") or data.get("createdTime")
        if not raw_ts:
            return None
        if isinstance(raw_ts, (int, float)):
            return datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
        dt = datetime.fromisoformat(str(raw_ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _emit_deletion_audit(resource_id: str, resource_type: str, extra: Dict[str, Any]) -> None:
    """Fire-and-forget audit event for a retention deletion."""
    audit_emit(
        AuditEvent(
            category=AuditCategory.SECURITY,
            action="retention_purge",
            actor_id="system:retention_worker",
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=extra,
        )
    )


async def _async_cleanup_expired_chats(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Remove chat sessions/conversations older than retention_days.

    Idempotent: re-running against already-deleted keys is safe.
    Returns counts for deleted_sessions, deleted_conversations, skipped, errors.
    """
    if retention_days <= 0:
        logger.info("Chat retention disabled (retention_days=%d), skipping.", retention_days)
        return {"deleted_sessions": 0, "deleted_conversations": 0, "skipped": 0, "errors": 0}

    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis client unavailable — skipping chat retention cleanup.")
        return {"deleted_sessions": 0, "deleted_conversations": 0, "skipped": 0, "errors": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted_sessions = 0
    deleted_conversations = 0
    skipped = 0
    errors = 0

    # Prune chat:recent sorted set entries older than cutoff
    cutoff_ts = cutoff.timestamp()
    try:
        if dry_run:
            count = redis_client.zcount(_RECENT_KEY, "-inf", cutoff_ts)
            logger.info("[DRY RUN] Would prune %d entries from %s older than %s", count, _RECENT_KEY, cutoff)
        else:
            removed = redis_client.zremrangebyscore(_RECENT_KEY, "-inf", cutoff_ts)
            deleted_sessions += removed
            if removed:
                logger.info("Pruned %d entries from %s (older than %s)", removed, _RECENT_KEY, cutoff)
    except Exception as exc:
        errors += 1
        logger.error("Failed to prune %s: %s", _RECENT_KEY, exc)

    # Scan and delete individual session keys
    for prefix, counter_attr in ((_SESSION_PREFIX, "sessions"), (_CONVERSATION_PREFIX, "conversations")):
        cursor: int = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=f"{prefix}*", count=200)
            for key in keys:
                try:
                    raw = redis_client.get(key)
                    if raw is None:
                        continue  # Already gone — idempotent

                    if _is_keep_forever(raw):
                        skipped += 1
                        continue

                    created_at = _parse_created_at(raw)
                    if created_at is None or created_at >= cutoff:
                        continue

                    age_days = (datetime.now(timezone.utc) - created_at).days
                    key_str = key.decode() if isinstance(key, bytes) else key

                    if dry_run:
                        logger.info("[DRY RUN] Would delete %s (age=%dd)", key_str, age_days)
                        if counter_attr == "sessions":
                            deleted_sessions += 1
                        else:
                            deleted_conversations += 1
                    else:
                        redis_client.delete(key)
                        _emit_deletion_audit(
                            resource_id=key_str,
                            resource_type=f"chat:{counter_attr[:-1]}",
                            extra={"age_days": age_days, "retention_days": retention_days},
                        )
                        if counter_attr == "sessions":
                            deleted_sessions += 1
                        else:
                            deleted_conversations += 1
                        logger.debug("Deleted %s (age=%dd)", key_str, age_days)
                except Exception as exc:
                    errors += 1
                    logger.error("Error processing key %s: %s", key, exc)
            if cursor == 0:
                break

    logger.info(
        "Chat retention: deleted_sessions=%d deleted_conversations=%d skipped=%d errors=%d "
        "retention_days=%d dry_run=%s",
        deleted_sessions,
        deleted_conversations,
        skipped,
        errors,
        retention_days,
        dry_run,
    )
    return {
        "deleted_sessions": deleted_sessions,
        "deleted_conversations": deleted_conversations,
        "skipped": skipped,
        "errors": errors,
    }


@celery_app.task(bind=True, name="tasks.cleanup_expired_chats")
def cleanup_expired_chats(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove chat sessions older than retention_days (GH#8995).

    retention_days defaults to AUTOBOT_CHAT_RETENTION_DAYS (0 = disabled).
    dry_run=True logs what would be deleted without making changes.
    """
    if retention_days is None:
        retention_days = _CHAT_RETENTION_DAYS
    return run_or_schedule(_async_cleanup_expired_chats(retention_days, dry_run))
