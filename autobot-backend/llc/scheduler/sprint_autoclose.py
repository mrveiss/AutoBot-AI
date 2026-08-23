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
from typing import TYPE_CHECKING, Optional

from celery import shared_task

from user_management.database import get_async_session_factory
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
)

if TYPE_CHECKING:  # import cost paid only by type checkers
    from ..services.sprint_autoclose import SprintAutoCloseService

logger = logging.getLogger(__name__)

# #13332: this module is imported EAGERLY by llc/scheduler/__init__.py, because
# that is the only way Celery's autodiscovery reaches the @shared_task below
# (GH#12318).  It therefore pays its import cost on every worker, beat process
# and API process — and importing SprintAutoCloseService at module level made
# that cost enormous and invisible:
#
#   llc.services.sprint_autoclose -> llc.kb.sprint_summarizer
#       -> llm_shared.types      (probes PyTorch/CUDA at import; logs
#                                 "PyTorch not available or CUDA libraries missing")
#       -> llc.kb.collections    (ChromaDB / knowledge stack)
#
# So merely touching `llc.scheduler.base` — three stdlib imports — booted the
# vector/LLM stack, which is the chain #13332 measured.  Deferring the service to
# first call keeps registration eager (the decorator still runs at import) while
# the expensive tail is paid only when the task actually executes, once a day.
#
# `_svc` stays a module attribute holding a single process-wide instance, so the
# construction semantics and any test that patches it are unchanged.
_svc: "Optional[SprintAutoCloseService]" = None


def _service() -> "SprintAutoCloseService":
    """Return the process-wide service, constructing it on first use (#13332)."""
    global _svc
    if _svc is None:
        from ..services.sprint_autoclose import SprintAutoCloseService

        _svc = SprintAutoCloseService()
    return _svc


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
    svc = _service()
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        sprints = await svc.check_and_queue(session)
        await session.commit()
    await svc.publish_queued(sprints)
    logger.info("Sprint auto-close daily check: %d sprints queued for approval", len(sprints))
    return len(sprints)


__all__ = ["run_daily_check", "_async_check"]
