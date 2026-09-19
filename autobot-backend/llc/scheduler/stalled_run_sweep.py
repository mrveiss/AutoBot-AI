# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Celery-beat sweep: close out heartbeat runs whose agent stopped reporting (#16817).

``llc_heartbeat_runs`` has always recorded that a run started. Nothing read it back
to decide a run had *stopped*. A run whose agent died mid-work therefore stayed
``running`` for ever, and the only thing that ever noticed was a person spotting an
inconsistency — which is how two abandoned runs were found on 2026-09-16, one of them
holding three already-merged worktrees that no live session could release.

The rule is deliberately narrow: a run that has been non-terminal for longer than
``LLC_RUN_STALL_TIMEOUT_SECONDS`` is marked ``TIMEOUT`` with an error that says the
sweep decided it, not the adapter. ``TIMEOUT`` is the existing status for "ran out of
time" and reusing it keeps the state machine as it is; the distinction that matters —
*we lost contact* versus *the adapter reported a timeout* — lives in ``error``, which
is what the reader needs to tell them apart.

What this sweep deliberately does NOT do is release what the run held. Claims,
assignments and workspace leases are released in #16818, which models the lease this
sweep will then have something to release. Marking a run stalled and leaving its
holdings is an improvement over never noticing, and it is not the finished job: a
status nobody acts on is close to what we have today.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import select

from autobot_shared.env_utils import env_int
from llc.models.enums import LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from user_management.database import get_async_session_factory
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
)

logger = logging.getLogger(__name__)

# Env-var-backed, never a literal at the call site. Six hours is longer than any
# adapter run observed to date and short enough that an abandoned run is noticed
# the same working day. Lower it and long legitimate runs get killed; raise it and
# the failure it exists to catch stays invisible for longer.
STALL_TIMEOUT_SECONDS = env_int("LLC_RUN_STALL_TIMEOUT_SECONDS", 6 * 60 * 60)

#: Statuses a run can sit in while still believed to be alive.
NON_TERMINAL_STATUSES = (LLCRunStatus.QUEUED.value, LLCRunStatus.RUNNING.value)

#: Written to ``error`` so a swept run is never mistaken for an adapter-reported
#: timeout. The text is asserted by the tests — it is the only thing that tells a
#: reader which of the two happened.
STALL_ERROR = "run stalled: no completion reported within {seconds}s; closed out by the stalled-run sweep (#16817)"


@shared_task(
    name="llc.scheduler.stalled_run_sweep.run_stalled_run_sweep",
    bind=True,
    base=DeadLetterTask,
    autoretry_for=CELERY_TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=CELERY_RETRY_BACKOFF_MAX,
    max_retries=CELERY_MAX_RETRIES,
)
def run_stalled_run_sweep(self: object) -> dict:  # type: ignore[type-arg]
    """Sync Celery entry point — closes out runs that stopped reporting."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    stalled = loop.run_until_complete(_async_sweep())
    return {"stalled": stalled}


def _cutoff(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) - timedelta(seconds=STALL_TIMEOUT_SECONDS)


async def _async_sweep() -> int:
    """Select non-terminal runs older than the cutoff and close them out."""
    factory = get_async_session_factory()
    cutoff = _cutoff()
    stalled = 0
    async with factory() as session:
        # started_at is NULL for a run that never got picked up; fall back to
        # created_at so a run that was queued and abandoned is swept too. A bare
        # ``started_at <= cutoff`` would exclude those rows through SQL
        # three-valued logic and strand them exactly as the disposal sweep found.
        result = await session.execute(
            select(LLCHeartbeatRun).where(
                LLCHeartbeatRun.status.in_(NON_TERMINAL_STATUSES),
                LLCHeartbeatRun.finished_at.is_(None),
            )
        )
        for run in result.scalars().all():
            age_anchor = run.started_at or run.created_at
            if age_anchor is None or age_anchor > cutoff:
                continue
            run.status = LLCRunStatus.TIMEOUT.value
            run.finished_at = datetime.now(timezone.utc)
            run.error = STALL_ERROR.format(seconds=STALL_TIMEOUT_SECONDS)
            stalled += 1
        await session.commit()
    # Logged unconditionally: a sweep that found nothing and a sweep that did not
    # run must not look the same in the logs.
    logger.info("Stalled-run sweep closed out %d run(s) older than %ds", stalled, STALL_TIMEOUT_SECONDS)
    return stalled


__all__ = ["run_stalled_run_sweep", "STALL_TIMEOUT_SECONDS", "STALL_ERROR", "NON_TERMINAL_STATUSES"]
