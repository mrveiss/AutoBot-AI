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
``LLC_RUN_STALL_TIMEOUT_SECONDS`` is marked ``STALLED`` with an error that says the
sweep decided it, not the adapter.

This reverses a decision recorded here, so the reason is recorded too. The original
reused ``TIMEOUT`` because that "keeps the state machine as it is", putting the
distinction — *we lost contact* versus *the adapter reported a timeout* — in ``error``.
The cost that was being avoided turns out to be close to zero: ``status`` is
``sa.String(32)`` rather than a native enum, so no migration; and ``is_terminal`` is a
deny-list over ``{QUEUED, RUNNING}``, so a new terminal member needs no edit there. And
the thing traded away is what #16817's AC4 asks for — *"the reason is recorded, not
inferred"*. With four sites setting ``TIMEOUT``, a consumer asking "which runs
stalled?" had to match a formatted, human-readable ``error`` string, which is inference
and breaks on a re-wording. ``error`` still carries the detail; ``status`` now carries
the fact.

Marking the run is only half of it. #16818 gave the workspace a lease, so this
sweep now releases what the run held: a stalled run hands its workspace back on the
same pass that closes it out. That is the half that was missing on 2026-09-16, when
one abandoned run held three already-merged worktrees and nothing could take them
back -- a status nobody acts on is close to never noticing at all.

The release frees the *slot*, not the directory. Whether the directory may be
removed is a separate question with its own evidence, and it is asked in
``llc.services.workspace_disposal``.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import func, select

from autobot_shared.env_utils import env_int
from llc.models.enums import LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.services.workspace_lease import release_for_run
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

#: Written to ``error`` for the human-readable detail. It is no longer the only
#: thing distinguishing a stall from an adapter timeout — ``STALLED`` is — so a
#: re-wording here can no longer make the two indistinguishable.
STALL_ERROR = "run stalled: no completion reported within {seconds}s; closed out by the stalled-run sweep (#16817)"

#: Written to the lease's ``release_reason``. A workspace handed back because its run
#: stalled reads differently from one whose lease simply expired, and the audit trail
#: keeps them apart -- the first means the run died, the second means the holder did.
STALL_RELEASE_REASON = "run stalled: workspace released by the stalled-run sweep (#16817/#16818)"


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


def _stalled_candidates(cutoff: datetime):
    """The rows this sweep may close out, as one statement.

    Extracted so the two properties that matter are assertable without a database:
    the age comparison happens in SQL, and the rows are locked with SKIP LOCKED.
    """
    # The age anchor: started_at is NULL for a run that never got picked up, so fall
    # back to created_at and a queued-then-abandoned run is swept too. A bare
    # ``started_at <= cutoff`` would exclude those rows through SQL three-valued
    # logic and strand them exactly as the disposal sweep found.
    #
    # #16817: that reasoning was right and the implementation did not follow it --
    # the comparison ran in Python over EVERY non-terminal row, so each sweep scanned
    # the whole live population to act on a few. COALESCE puts the same rule in SQL.
    age_anchor = func.coalesce(LLCHeartbeatRun.started_at, LLCHeartbeatRun.created_at)
    return (
        select(LLCHeartbeatRun).where(
            LLCHeartbeatRun.status.in_(NON_TERMINAL_STATUSES),
            LLCHeartbeatRun.finished_at.is_(None),
            age_anchor.is_not(None),
            age_anchor <= cutoff,
        )
        # #16817 AC5: two beat workers can overlap. Today both would write the same
        # terminal status and the race would be invisible. #16818 adds the release of
        # claims, assignments and workspace leases to this path, and the same race
        # then releases each holding twice. SKIP LOCKED makes the sweep partition
        # rather than collide, so the lock is in place BEFORE the side effects that
        # need it -- a defect armed by its own dependency is cheaper to prevent than
        # to diagnose.
        .with_for_update(skip_locked=True)
    )


async def _async_sweep() -> int:
    """Select non-terminal runs older than the cutoff and close them out."""
    factory = get_async_session_factory()
    cutoff = _cutoff()
    stalled = 0
    released = 0
    async with factory() as session:
        # The age anchor: started_at is NULL for a run that never got picked up, so
        # fall back to created_at and a queued-then-abandoned run is swept too. A bare
        # ``started_at <= cutoff`` would exclude those rows through SQL three-valued
        # logic and strand them exactly as the disposal sweep found.
        #
        # #16817: that reasoning was right and the implementation did not follow it --
        # the comparison ran in Python over EVERY non-terminal row, so each sweep
        # scanned the whole live population to act on a few. COALESCE puts the same
        # rule in SQL, where the index can serve it.
        result = await session.execute(_stalled_candidates(cutoff))
        for run in result.scalars().all():
            run.status = LLCRunStatus.STALLED.value
            run.finished_at = datetime.now(timezone.utc)
            run.error = STALL_ERROR.format(seconds=STALL_TIMEOUT_SECONDS)
            stalled += 1
            # Inside the same transaction as the status write, and under the same
            # SKIP LOCKED selection: a run that this worker did not claim is not
            # this worker's to release, so the two can never disagree about who
            # closed the run out.
            released += len(await release_for_run(session, run.id, STALL_RELEASE_REASON))
        await session.commit()
    # Logged unconditionally: a sweep that found nothing and a sweep that did not
    # run must not look the same in the logs.
    logger.info(
        "Stalled-run sweep closed out %d run(s) older than %ds and released %d workspace lease(s)",
        stalled,
        STALL_TIMEOUT_SECONDS,
        released,
    )
    return stalled


__all__ = [
    "run_stalled_run_sweep",
    "STALL_TIMEOUT_SECONDS",
    "STALL_ERROR",
    "STALL_RELEASE_REASON",
    "NON_TERMINAL_STATUSES",
]
