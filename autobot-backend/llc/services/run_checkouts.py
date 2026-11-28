# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The work-item checkouts a heartbeat run made, and how they are given back (#19601, #19600).

A checkout is linked to its run by ``LLCWorkItem.checkout_run_id`` and by nothing else. There is
exactly one release of them, used by every path that ends a run (the stalled-run sweep, a manual
cancel, the liveness monitor), so no path can leave a checkout, or its Redis fence, behind.

``LLCHeartbeatRun.work_item_id`` is not read here: nothing ever wrote it, and a run can hold any
number of items, which one column cannot name.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Select, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from ..models.activity import ActorType
from ..models.enums import ActivityEventType, LLCRunStatus, WorkItemStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.work_item import LLCWorkItem
from .activity_log import LLCActivityLogService
from .work_item_own_task import checkout_fence_key, drop_fence_of_generation

logger = get_logger(__name__)

#: Statuses a run can sit in while still believed to be alive.
NON_TERMINAL_STATUSES = (LLCRunStatus.QUEUED.value, LLCRunStatus.RUNNING.value)

#: Append-only audit sink for checkout releases. Module-level so tests can swap it.
_activity_log = LLCActivityLogService()


@dataclass(frozen=True)
class ReleasedCheckout:
    """A checkout cleared in the caller's transaction, and the fence to drop once that commits."""

    item: LLCWorkItem
    fence_key: str
    generation: str  #: the run id the fence is tagged with; the fence is dropped only while it carries it
    moved: bool = False  #: the item was still ``in_progress`` and was returned to ``ReleaseWhy.then``


def checkouts_held_by(run_id: uuid.UUID | str, company_id: uuid.UUID | str) -> Select:
    """Work items of the run's company whose checkout this run made. The run-scoped claim, by its own key.

    The company bounds it: ``checkout_run_id`` is free text a manual checkout can set, so a run id alone must
    not reach an item of another company.

    Plain ``FOR UPDATE`` (not SKIP LOCKED): an item another transaction is touching is waited for, and
    Postgres re-checks the predicate once the lock is granted, so an item released or re-checked-out
    meanwhile drops out instead of being cleared.
    """
    return (
        select(LLCWorkItem)
        .where(LLCWorkItem.checkout_run_id == str(run_id), LLCWorkItem.company_id == uuid.UUID(str(company_id)))
        .with_for_update()
    )


@dataclass(frozen=True)
class ReleaseWhy:
    """Why a run's checkouts are released, and who did it, as the activity row records them."""

    reason: str
    source: str
    actor_type: ActorType = ActorType.SYSTEM
    actor_id: Optional[str] = None
    log: Optional[LLCActivityLogService] = None
    #: Where an item still ``in_progress`` goes: ``ready`` (claimable again) unless the caller needs a human to look.
    then: WorkItemStatus = WorkItemStatus.READY


def _return_status(item: LLCWorkItem, then: WorkItemStatus) -> bool:
    """Move an item still ``in_progress`` to *then*; any other status is left exactly as it is.

    This is the system's write, not a user transition: it undoes the ``ready -> in_progress`` write that
    ``stamp_agent_checkout`` makes when a run checks the item out, so it is deliberately absent from
    ``_ALLOWED_TRANSITIONS`` (a person cannot move an item back to ``ready`` from ``in_progress``). An item in
    review, blocked, done or cancelled changed state on its own after the checkout and keeps that state.

    The undo also clears ``checkout_intent``, which belongs to the claim that is ending. ``started_at`` is left
    as it is: the first claim time stays the start of the work, however many runs it takes.
    """
    if item.status != WorkItemStatus.IN_PROGRESS:
        return False
    item.status = then
    item.checkout_intent = None
    return True


async def _release_one(session: AsyncSession, item: LLCWorkItem, run_id, why: ReleaseWhy) -> ReleasedCheckout:
    """Clear one checkout, return an unfinished item to the queue and record both, in the caller's transaction."""
    held, was = item.checkout_run_id, WorkItemStatus(item.status).value
    released = ReleasedCheckout(item, checkout_fence_key(item.id), held, _return_status(item, why.then))
    item.checkout_run_id = None
    item.checkout_locked_at = None
    item.version += 1
    before, after = {"checkout_run_id": held}, {"checkout_run_id": None}
    if released.moved:
        before["status"], after["status"] = was, WorkItemStatus(item.status).value
    await (why.log or _activity_log).record(
        session,
        company_id=str(item.company_id),
        actor_type=why.actor_type,
        actor_id=why.actor_id,
        event_type=ActivityEventType.WORK_ITEM_UPDATED,
        entity_type="work_item",
        entity_id=str(item.id),
        before=before,
        after=after,
        metadata={"reason": why.reason, "heartbeat_run_id": str(run_id), "source": why.source},
    )
    return released


async def release_checkouts_for_run(
    session: AsyncSession, run: LLCHeartbeatRun, why: ReleaseWhy
) -> list[ReleasedCheckout]:
    """Release every work-item checkout *run* made; idempotent by its predicate. The one release, for every caller.

    An item still ``in_progress`` goes back to ``ready`` so the queue offers it again (``eligible_for`` reads
    ``ready`` and no checkout), or to ``ReleaseWhy.then`` where the caller wants a person to look. Items in any
    other status are not touched beyond the checkout. The assignment is kept: it records who the item belongs
    to, not which run made it so. Redis is untouched here -- hand the result to :func:`drop_released_fences`
    after the caller commits.

    Known window: a fence whose drop fails, or never runs because the process dies between the commit and the
    drop, stays up to the checkout TTL while the database already says the item is free. ``checkout`` checks
    the fence before the row, so another agent's checkout of that item is refused until the TTL expires; the
    same agent is not. The fence is a fast path, the database authoritative, and the window is bounded.

    The run's own status write (cancelled, stalled, interrupted) is flushed first, so it holds the run row's
    lock before the checkouts are selected and a claim racing it cannot slip in unreleased.
    """
    # The session runs with autoflush off: write the caller's terminal status now, so the run row is locked
    # (a concurrent claim's FOR SHARE in ``live_run_id`` then waits) before the checkouts are selected.
    await session.flush()
    run_id = str(run.id)
    result = await session.execute(checkouts_held_by(run_id, run.company_id))
    held = [item for item in result.scalars().all() if item.checkout_run_id == run_id]
    return [await _release_one(session, item, run_id, why) for item in held]


async def drop_released_fences(released: list[ReleasedCheckout]) -> None:
    """Drop each released item's Redis fence, after the DB release has committed.

    The fence (``llc:checkout:{id}``, value = agent tagged with the run) is a fast path in front of the row
    lock, not the lock itself, and it carries its own TTL. A fence tagged with another run belongs to a newer
    checkout and is left alone. Nothing here may fail the caller: the DB release is authoritative, and a fence
    left behind expires on its TTL.
    """
    if not released:
        return
    try:
        redis = await get_async_redis_client()
    except Exception as exc:
        logger.warning("No Redis client for %d released checkout fence(s): %s", len(released), exc)
        return
    if redis is None:
        return
    for fence in released:
        try:
            await drop_fence_of_generation(redis, fence.fence_key, fence.generation)
        except Exception as exc:
            logger.warning("Could not drop checkout fence %s: %s", fence.fence_key, exc)


async def live_run_id(session: AsyncSession, agent_slug: str, company_id: str) -> Optional[uuid.UUID]:
    """The run this agent is working in right now, or ``None``: its RUNNING run, else its newest QUEUED one.

    The run row is read ``FOR SHARE`` and stays locked until the caller's transaction ends, so a cancel (an
    UPDATE of that row) waits for the claim and its own release then sees it. Postgres re-evaluates the
    non-terminal predicate once the lock is granted, so a run cancelled meanwhile is not returned.

    A running run asking for work must stamp its own id: a newer queued run may be skipped, which is terminal
    and never swept, and a checkout stamped with it would be orphaned.

    ``LLCHeartbeatRun.agent_id`` is the agent's slug (``agent_org_nodes.agent_id``), which is what the agent
    credential carries; the checkout itself is keyed on the node uuid.
    """
    result = await session.execute(
        select(LLCHeartbeatRun.id)
        .where(
            LLCHeartbeatRun.agent_id == agent_slug,
            LLCHeartbeatRun.company_id == uuid.UUID(company_id),
            LLCHeartbeatRun.status.in_(NON_TERMINAL_STATUSES),
            LLCHeartbeatRun.finished_at.is_(None),
        )
        .order_by(
            case((LLCHeartbeatRun.status == LLCRunStatus.RUNNING.value, 0), else_=1), LLCHeartbeatRun.created_at.desc()
        )
        .limit(1)
        .with_for_update(read=True)
    )
    return result.scalar_one_or_none()
