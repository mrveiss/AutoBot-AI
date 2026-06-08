# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery beat task: nightly snapshot cleanup based on TTL (GH#4458, MVA-2228).

Removes Docker snapshots older than AUTOBOT_SNAPSHOT_TTL_DAYS to prevent
unbounded storage growth in long-running deployments.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from celery_app import celery_app

logger = get_logger(__name__)

_DEFAULT_TTL_DAYS = 7


async def _async_cleanup_expired_snapshots(ttl_days: int) -> Dict[str, int]:
    """Remove snapshots older than TTL (async helper for Celery task)."""
    from services.execution.docker_backend import _SYSTEM_CALLER, DockerBackend

    backend = lazy_singleton(DockerBackend)
    snapshots = backend._snapshot_index.list_all()

    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    deleted = 0
    errors = 0

    for record in snapshots:
        created = datetime.fromisoformat(record.created_at)
        # Normalize naive datetimes from legacy records (GH#9236)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days

        if created < cutoff:
            try:
                await backend.delete_snapshot(record.snapshot_id, caller_user_id=_SYSTEM_CALLER)
                deleted += 1
                logger.info(
                    "Deleted snapshot %s (age: %d days, size: %d bytes)",
                    record.snapshot_id,
                    age_days,
                    record.size_bytes,
                )
            except Exception as exc:
                errors += 1
                logger.error("Failed to delete snapshot %s: %s", record.snapshot_id, exc)

    logger.info(
        "Snapshot cleanup: deleted=%d, errors=%d, ttl_days=%d",
        deleted,
        errors,
        ttl_days,
    )
    return {"deleted": deleted, "errors": errors}


@celery_app.task(bind=True, name="tasks.cleanup_expired_snapshots")
def cleanup_expired_snapshots(self, ttl_days: int = None) -> Dict[str, int]:
    """Remove snapshots older than TTL (GH#4458, MVA-2228).

    Args:
        ttl_days: Number of days to retain snapshots. Defaults to
                  AUTOBOT_SNAPSHOT_TTL_DAYS env var or 7 days.

    Returns:
        Dict with "deleted" and "errors" counts.
    """
    if ttl_days is None:
        ttl_days = int(os.getenv("AUTOBOT_SNAPSHOT_TTL_DAYS", _DEFAULT_TTL_DAYS))

    return run_or_schedule(_async_cleanup_expired_snapshots(ttl_days))
