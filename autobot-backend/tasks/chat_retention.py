# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery beat task: chat history retention cleanup (GH#8995, MVA-3044).

Removes chat sessions and conversations older than the configured TTL to prevent
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

_DEFAULT_CHAT_RETENTION_DAYS = 90


async def _async_cleanup_expired_chats(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Remove chat sessions older than retention_days (async helper for Celery task).

    Args:
        retention_days: Number of days to retain chat sessions
        dry_run: If True, log what would be deleted without actually deleting

    Returns:
        Dict with "deleted_sessions", "deleted_conversations", and "errors" counts
    """
    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis client not available, skipping chat retention cleanup")
        return {"deleted_sessions": 0, "deleted_conversations": 0, "errors": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_timestamp = cutoff.timestamp()

    deleted_sessions = 0
    deleted_conversations = 0
    errors = 0

    try:
        # Cleanup chat:recent sorted set - remove entries older than retention window
        # ZREMRANGEBYSCORE chat:recent -inf <cutoff_timestamp>
        recent_key = "chat:recent"
        if dry_run:
            old_count = redis_client.zcount(recent_key, "-inf", cutoff_timestamp)
            logger.info(
                "[DRY RUN] Would remove %d old entries from %s (older than %s)",
                old_count,
                recent_key,
                cutoff.isoformat(),
            )
        else:
            removed = redis_client.zremrangebyscore(recent_key, "-inf", cutoff_timestamp)
            deleted_sessions += removed
            logger.info(
                "Removed %d old entries from %s (older than %s)",
                removed,
                recent_key,
                cutoff.isoformat(),
            )

        # Cleanup individual chat:session:* keys
        # Scan for keys and check their creation time via OBJECT IDLETIME
        session_pattern = "chat:session:*"
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=session_pattern, count=100)
            for key in keys:
                try:
                    # OBJECT IDLETIME returns seconds since last access
                    idle_time = redis_client.object("IDLETIME", key)
                    if idle_time is None:
                        continue

                    # Convert idle time to age and compare with retention window
                    idle_days = idle_time / 86400
                    if idle_days > retention_days:
                        if dry_run:
                            logger.info("[DRY RUN] Would delete session key: %s (idle: %.1f days)", key, idle_days)
                        else:
                            redis_client.delete(key)
                            deleted_sessions += 1
                            if deleted_sessions % 100 == 0:
                                logger.info("Deleted %d session keys so far...", deleted_sessions)
                except Exception as exc:
                    errors += 1
                    logger.error("Failed to process session key %s: %s", key, exc)

            if cursor == 0:
                break

        # Cleanup chat:conversation:* keys
        conversation_pattern = "chat:conversation:*"
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=conversation_pattern, count=100)
            for key in keys:
                try:
                    idle_time = redis_client.object("IDLETIME", key)
                    if idle_time is None:
                        continue

                    idle_days = idle_time / 86400
                    if idle_days > retention_days:
                        if dry_run:
                            logger.info("[DRY RUN] Would delete conversation key: %s (idle: %.1f days)", key, idle_days)
                        else:
                            redis_client.delete(key)
                            deleted_conversations += 1
                            if deleted_conversations % 100 == 0:
                                logger.info("Deleted %d conversation keys so far...", deleted_conversations)
                except Exception as exc:
                    errors += 1
                    logger.error("Failed to process conversation key %s: %s", key, exc)

            if cursor == 0:
                break

    except Exception as exc:
        errors += 1
        logger.error("Chat retention cleanup failed: %s", exc)

    logger.info(
        "Chat retention cleanup: sessions=%d, conversations=%d, errors=%d, days=%d, dry_run=%s",
        deleted_sessions,
        deleted_conversations,
        errors,
        retention_days,
        dry_run,
    )
    return {
        "deleted_sessions": deleted_sessions,
        "deleted_conversations": deleted_conversations,
        "errors": errors,
    }


@celery_app.task(bind=True, name="tasks.cleanup_expired_chats")
def cleanup_expired_chats(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove chat sessions and conversations older than retention_days (GH#8995, MVA-3044).

    Args:
        retention_days: Number of days to retain chats. Defaults to
                        AUTOBOT_CHAT_RETENTION_DAYS env var or 90 days.
        dry_run: If True, log what would be deleted without actually deleting.

    Returns:
        Dict with "deleted_sessions", "deleted_conversations", and "errors" counts.
    """
    if retention_days is None:
        retention_days = int(os.getenv("AUTOBOT_CHAT_RETENTION_DAYS", _DEFAULT_CHAT_RETENTION_DAYS))

    return run_or_schedule(_async_cleanup_expired_chats(retention_days, dry_run))
