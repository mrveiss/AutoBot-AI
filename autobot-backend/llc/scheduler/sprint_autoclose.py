# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
)

from ..services.sprint_autoclose import SprintAutoCloseService

logger = logging.getLogger(__name__)

_svc = SprintAutoCloseService()


# #11586: transient errors (ConnectionError/TimeoutError/OSError) retry with
# jittered exponential backoff; validation errors fail fast; terminal failures
# are parked in the Redis dead-letter list by DeadLetterTask.
@shared_task(
    name="llc.scheduler.sprint_autoclose.run_daily_check",
    bind=True,
    base=DeadLetterTask,
    autoretry_for=CELERY_TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=CELERY_RETRY_BACKOFF_MAX,
    max_retries=CELERY_MAX_RETRIES,
)
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
