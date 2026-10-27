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

Marking the run is only half of it. On the same pass, in the same transaction and
under the same ``SKIP LOCKED`` row lock, the sweep releases exactly what the run
itself acquired, and nothing else:

1. **Workspace leases** -- every ``LLCWorkspaceLease`` whose ``heartbeat_run_id`` is
   the run (``release_for_run``), reason ``STALL_RELEASE_REASON``.
2. **Work-item checkouts** -- every ``LLCWorkItem`` whose ``checkout_run_id`` is the
   run: ``checkout_run_id`` and ``checkout_locked_at`` cleared, ``version`` bumped,
   one ``work_item.updated`` activity entry each with ``reason="stalled"``. After the
   commit, the item's ``llc:checkout:{id}`` Redis fence is dropped when it still
   names the checkout's holder.

That is the half that was missing on 2026-09-16, when one abandoned run held three
already-merged worktrees and nothing could take them back -- a status nobody acts on
is close to never noticing at all.

What it deliberately does NOT release is the **assignment**. ``assignee_agent_id``
records who the item belongs to, not which run made it so: an item assigned to an
agent before the run started would be unassigned because the run died, which is a
reassignment decision, not a release. The checkout is the run-scoped claim; the
assignment stays.

The release frees the *slot*, not the directory. Whether the directory may be
removed is a separate question with its own evidence, and it is asked in
``llc.services.workspace_disposal``.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import func, select

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value
from llc.models.activity import ActorType
from llc.models.enums import ActivityEventType, LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.models.work_item import LLCWorkItem
from llc.services.activity_log import LLCActivityLogService
from llc.services.workspace_lease import release_for_run
from user_management.database import get_async_session_factory
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
)

logger = get_logger(__name__)

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

#: The ``reason`` on a released checkout's activity entry. ``stalled`` rather than
#: ``failed`` or ``cancelled``: the run did not report an outcome, the sweep decided
#: it had none (#16817 AC4).
STALL_CHECKOUT_REASON = LLCRunStatus.STALLED.value

#: Append-only audit sink for checkout releases. Module-level so tests can swap it.
_activity_log = LLCActivityLogService()


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
    return loop.run_until_complete(_async_sweep())


def stall_cutoff(now: datetime | None = None) -> datetime:
    """The instant before which a non-terminal run counts as stalled.

    Public because ``run_status`` asks the same question (#19582 review): a run this
    sweep would close out no longer counts as the agent being busy.
    """
    return (now or datetime.now(timezone.utc)) - timedelta(seconds=STALL_TIMEOUT_SECONDS)


def run_age_anchor(entity=LLCHeartbeatRun):  # noqa: ANN001,ANN201 - an ORM entity or alias
    """How old a run is: ``started_at``, else ``created_at`` for one never picked up.

    One definition for this sweep and ``run_status``'s busy check (#19582 review).
    """
    return func.coalesce(entity.started_at, entity.created_at)


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
    age_anchor = run_age_anchor()
    return (
        select(LLCHeartbeatRun).where(
            LLCHeartbeatRun.status.in_(NON_TERMINAL_STATUSES),
            LLCHeartbeatRun.finished_at.is_(None),
            age_anchor.is_not(None),
            age_anchor <= cutoff,
        )
        # #16817 AC5: two beat workers can overlap. SKIP LOCKED makes them partition
        # the runs rather than collide, so each run -- and so each lease and checkout
        # it holds -- is released by exactly one sweeper.
        .with_for_update(skip_locked=True)
    )


def _checkouts_held_by(run_id):
    """Work items whose checkout this run made. The run-scoped claim, by its own key.

    Plain ``FOR UPDATE`` (not SKIP LOCKED): an item another transaction is touching
    is waited for, and Postgres re-checks the predicate once the lock is granted, so
    an item released or re-checked-out meanwhile drops out instead of being cleared.
    """
    return select(LLCWorkItem).where(LLCWorkItem.checkout_run_id == str(run_id)).with_for_update()


async def _release_checkout(session, item: LLCWorkItem, run_id) -> None:
    """Clear one checkout the run held and record why, in the caller's transaction."""
    held = item.checkout_run_id
    item.checkout_run_id = None
    item.checkout_locked_at = None
    item.version += 1
    await _activity_log.record(
        session,
        company_id=str(item.company_id),
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        event_type=ActivityEventType.WORK_ITEM_UPDATED,
        entity_type="work_item",
        entity_id=str(item.id),
        before={"checkout_run_id": held},
        after={"checkout_run_id": None},
        metadata={"reason": STALL_CHECKOUT_REASON, "heartbeat_run_id": str(run_id), "source": "stalled_run_sweep"},
    )


async def release_checkouts_for_run(session, run_id) -> list[LLCWorkItem]:
    """Release every work-item checkout *run_id* made; idempotent by its predicate."""
    result = await session.execute(_checkouts_held_by(run_id))
    items = [item for item in result.scalars().all() if item.checkout_run_id == str(run_id)]
    for item in items:
        await _release_checkout(session, item, run_id)
    return items


async def _drop_checkout_fences(fences: list[tuple[str, str]]) -> None:
    """Drop each released item's Redis fence, after the DB release has committed.

    The fence (``llc:checkout:{id}``, value = holder) is a fast path in front of the
    row lock, not the lock itself, and it carries its own TTL. A fence that now names
    a different holder belongs to a newer checkout and is left alone -- decided in one
    atomic compare-and-delete, so a checkout landing mid-release keeps its fence.
    Nothing here may fail the task: the DB release is authoritative and has already
    committed, and a fence left behind expires on its TTL.
    """
    if not fences:
        return
    try:
        redis = await get_async_redis_client()
    except Exception as exc:
        logger.warning("Stalled-run sweep has no Redis client for %d checkout fence(s): %s", len(fences), exc)
        return
    if redis is None:
        return
    for item_id, holder in fences:
        key = f"llc:checkout:{item_id}"
        try:
            await delete_if_value(redis, key, holder)
        except Exception as exc:
            logger.warning("Stalled-run sweep could not drop checkout fence %s: %s", key, exc)


def _mark_stalled(run: LLCHeartbeatRun) -> None:
    run.status = LLCRunStatus.STALLED.value
    run.finished_at = datetime.now(timezone.utc)
    run.error = STALL_ERROR.format(seconds=STALL_TIMEOUT_SECONDS)


async def _release_held(session, run: LLCHeartbeatRun, report: dict, fences: list) -> None:
    """Everything the run acquired, inside the transaction that marks it stalled."""
    leases = await release_for_run(session, run.id, STALL_RELEASE_REASON)
    items = await release_checkouts_for_run(session, run.id)
    report["workspace_leases"] += len(leases)
    report["checkouts"] += len(items)
    # Source of truth for the holder: checkout() SETs its agent_id as the fence value
    # (llc/services/work_item_service.py:490) and writes the same agent_id to
    # assignee_agent_id in that transaction (:513). A later reassignment makes the two
    # differ; the fence is then left to its TTL, never deleted from under its holder.
    fences.extend((str(item.id), str(item.assignee_agent_id)) for item in items if item.assignee_agent_id)


async def _async_sweep() -> dict:
    """Close out non-terminal runs older than the cutoff and release what they held."""
    factory = get_async_session_factory()
    report = {"stalled": 0, "workspace_leases": 0, "checkouts": 0}
    fences: list[tuple[str, str]] = []
    async with factory() as session:
        result = await session.execute(_stalled_candidates(stall_cutoff()))
        for run in result.scalars().all():
            _mark_stalled(run)
            report["stalled"] += 1
            # Same transaction and same SKIP LOCKED selection as the status write: a
            # run this worker did not claim is not this worker's to release.
            await _release_held(session, run, report, fences)
        await session.commit()
    await _drop_checkout_fences(fences)
    # Logged unconditionally: a sweep that found nothing and a sweep that did not
    # run must not look the same in the logs.
    logger.info(
        "Stalled-run sweep closed out %d run(s) older than %ds; released %d workspace lease(s) and %d checkout(s)",
        report["stalled"],
        STALL_TIMEOUT_SECONDS,
        report["workspace_leases"],
        report["checkouts"],
    )
    return report


__all__ = [
    "run_stalled_run_sweep",
    "STALL_TIMEOUT_SECONDS",
    "STALL_ERROR",
    "STALL_RELEASE_REASON",
    "STALL_CHECKOUT_REASON",
    "release_checkouts_for_run",
    "NON_TERMINAL_STATUSES",
    "run_age_anchor",
    "stall_cutoff",
]
