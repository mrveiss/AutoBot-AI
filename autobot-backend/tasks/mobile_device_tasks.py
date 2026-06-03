# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mobile Device Cleanup Tasks (GH#4463)

Periodic Celery tasks for pruning stale mobile devices.
"""

from datetime import timedelta

from celery import shared_task
from sqlalchemy import delete, select

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

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
            return {"deleted_count": 0, "dry_run": dry_run}

        if dry_run:
            logger.info("[DRY RUN] Would prune %d stale mobile device(s)", count)
            return {"deleted_count": count, "dry_run": True}

        # Delete stale devices
        device_ids = [d.id for d in stale_devices]
        await session.execute(delete(MobileDevice).where(MobileDevice.id.in_(device_ids)))
        await session.commit()
        logger.info("Pruned %d stale mobile device(s)", count)
        return {"deleted_count": count, "dry_run": False}
