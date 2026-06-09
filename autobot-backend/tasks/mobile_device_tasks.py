# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Mobile Device Cleanup Tasks (GH#4463)

Periodic Celery tasks for pruning stale mobile devices.
"""

from datetime import timedelta

from celery import shared_task
from sqlalchemy import delete, select

from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)
metrics = get_metrics_manager()

_DEVICE_EXPIRY_DAYS = 90


@shared_task(name="tasks.cleanup_stale_mobile_devices")
def cleanup_stale_mobile_devices(dry_run: bool = False) -> dict:
    """Prune mobile devices inactive for 90+ days.

    Args:
        dry_run: If True, only count devices without deleting.

    Returns:
        Dict with keys: deleted_count, dry_run
    """
    import asyncio

    result = asyncio.run(_cleanup_stale_devices_async(dry_run))
    return result


async def _cleanup_stale_devices_async(dry_run: bool) -> dict:
    """Async implementation of stale device cleanup."""
    from models.mobile_device import MobileDevice
    from user_management.database import get_async_session_factory

    cutoff = now_utc() - timedelta(days=_DEVICE_EXPIRY_DAYS)

    factory = get_async_session_factory()
    async with factory() as session:
        # Find stale devices (last_seen_at older than 90 days or NULL and created > 90 days ago)
        result = await session.execute(
            select(MobileDevice).where(
                (MobileDevice.last_seen_at.isnot(None) & (MobileDevice.last_seen_at < cutoff))
                | (MobileDevice.last_seen_at.is_(None) & (MobileDevice.created_at < cutoff))
            )
        )
        stale_devices = list(result.scalars().all())
        count = len(stale_devices)

        if count == 0:
            logger.info("No stale mobile devices to prune")
            # GH#4463: Update active device count after cleanup (even if no devices removed)
            await _update_active_device_count_async(session)
            return {"deleted_count": 0, "dry_run": dry_run}

        if dry_run:
            logger.info("[DRY RUN] Would prune %d stale mobile device(s)", count)
            return {"deleted_count": count, "dry_run": True}

        # Delete stale devices
        device_ids = [d.id for d in stale_devices]
        await session.execute(delete(MobileDevice).where(MobileDevice.id.in_(device_ids)))
        await session.commit()
        logger.info("Pruned %d stale mobile device(s)", count)
        # GH#4463: Record cleanup metrics and update active device count
        metrics.record_device_cleanup_removed(count)
        await _update_active_device_count_async(session)
        return {"deleted_count": count, "dry_run": False}


async def _update_active_device_count_async(session) -> None:
    """Update the active device count gauge for each platform.

    GH#4463: Called after cleanup to keep the active_device_count gauge accurate.
    """
    from sqlalchemy import func

    from models.mobile_device import MobileDevice

    cutoff = now_utc() - timedelta(days=_DEVICE_EXPIRY_DAYS)

    # Count active devices per platform
    result = await session.execute(
        select(
            MobileDevice.platform,
            func.count(MobileDevice.id).label("count"),
        )
        .where(
            (MobileDevice.last_seen_at.isnot(None) & (MobileDevice.last_seen_at >= cutoff))
            | (MobileDevice.last_seen_at.is_(None) & (MobileDevice.created_at >= cutoff))
        )
        .group_by(MobileDevice.platform)
    )

    # Update metrics for each platform
    platform_counts = {row.platform: row.count for row in result}
    for platform in ["ios", "android", "pwa"]:
        count = platform_counts.get(platform, 0)
        metrics.set_active_device_count(platform, count)
        logger.debug("Active %s devices: %d", platform, count)
