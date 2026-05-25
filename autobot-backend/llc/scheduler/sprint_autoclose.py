# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Sprint auto-close scheduler (GH#8224).

``SprintAutoCloseScheduler.run_daily_check`` is the Celery periodic task entry
point.  It delegates to ``SprintAutoCloseService.check_and_queue`` so each
worker call is idempotent and race-safe (SELECT ... FOR UPDATE SKIP LOCKED).

Celery beat schedule entry:
    "llc-sprint-autoclose-daily": {
        "task": "llc.scheduler.sprint_autoclose.run_daily_check",
        "schedule": crontab(hour=0, minute=5),  # 00:05 UTC daily
    }

The schedule is registered in celery_app.py so that beat picks it up.
"""

import logging

from celery import shared_task

from user_management.database import get_async_session_factory

from ..services.sprint_autoclose import SprintAutoCloseService

logger = logging.getLogger(__name__)

_svc = SprintAutoCloseService()


@shared_task(name="llc.scheduler.sprint_autoclose.run_daily_check", bind=True, max_retries=3)
def run_daily_check(self: object) -> dict:  # type: ignore[type-arg]
    """Celery task — detects expired sprints and queues SPRINT_CLOSE approvals.

    Designed to run once daily at 00:05 UTC via Celery beat.  The task is
    synchronous at the Celery layer; async DB access is wrapped with
    asyncio.run_coroutine_threadsafe inside the session factory helper.
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    queued_count = loop.run_until_complete(_async_check())
    return {"queued": queued_count}


async def _async_check() -> int:
    """Inner async body — separate function so it's unit-testable."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        sprints = await _svc.check_and_queue(session)
        await session.commit()
    await _svc.publish_queued(sprints)
    logger.info("Sprint auto-close daily check: %d sprints queued for approval", len(sprints))
    return len(sprints)


__all__ = ["run_daily_check", "_async_check"]
