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

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value

from ..models.activity import ActorType
from ..models.enums import ActivityEventType, LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.work_item import LLCWorkItem
from .activity_log import LLCActivityLogService
from .work_item_own_task import checkout_fence_key, checkout_fence_value

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
    fence_value: Optional[str]


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


def _fence_of(item: LLCWorkItem) -> Optional[str]:
    """The fence value this checkout wrote: its agent tagged with the run (the checkout generation)."""
    if not item.assignee_agent_id:
        return None
    return checkout_fence_value(str(item.assignee_agent_id), item.checkout_run_id)


@dataclass(frozen=True)
class ReleaseWhy:
    """Why a run's checkouts are released, and who did it, as the activity row records them."""

    reason: str
    source: str
    actor_type: ActorType = ActorType.SYSTEM
    actor_id: Optional[str] = None
    log: Optional[LLCActivityLogService] = None


async def _release_one(session: AsyncSession, item: LLCWorkItem, run_id, why: ReleaseWhy) -> ReleasedCheckout:
    """Clear one checkout and record why, in the caller's transaction."""
    released = ReleasedCheckout(item, checkout_fence_key(item.id), _fence_of(item))
    held = item.checkout_run_id
    item.checkout_run_id = None
    item.checkout_locked_at = None
    item.version += 1
    await (why.log or _activity_log).record(
        session,
        company_id=str(item.company_id),
        actor_type=why.actor_type,
        actor_id=why.actor_id,
        event_type=ActivityEventType.WORK_ITEM_UPDATED,
        entity_type="work_item",
        entity_id=str(item.id),
        before={"checkout_run_id": held},
        after={"checkout_run_id": None},
        metadata={"reason": why.reason, "heartbeat_run_id": str(run_id), "source": why.source},
    )
    return released


async def release_checkouts_for_run(
    session: AsyncSession, run: LLCHeartbeatRun, why: ReleaseWhy
) -> list[ReleasedCheckout]:
    """Release every work-item checkout *run* made; idempotent by its predicate.

    The assignment is kept: it records who the item belongs to, not which run made it so. Redis is
    untouched here -- hand the result to :func:`drop_released_fences` after the caller commits.
    """
    run_id = str(run.id)
    result = await session.execute(checkouts_held_by(run_id, run.company_id))
    held = [item for item in result.scalars().all() if item.checkout_run_id == run_id]
    return [await _release_one(session, item, run_id, why) for item in held]


async def drop_released_fences(released: list[ReleasedCheckout]) -> None:
    """Drop each released item's Redis fence, after the DB release has committed.

    The fence (``llc:checkout:{id}``, value = agent tagged with the run) is a fast path in front of the row
    lock, not the lock itself, and it carries its own TTL. A fence now naming another value belongs to a newer
    checkout and is left alone -- decided in one atomic compare-and-delete. Nothing here may fail the caller:
    the DB release is authoritative, and a fence left behind expires on its TTL.
    """
    fences = [r for r in released if r.fence_value]
    if not fences:
        return
    try:
        redis = await get_async_redis_client()
    except Exception as exc:
        logger.warning("No Redis client for %d released checkout fence(s): %s", len(fences), exc)
        return
    if redis is None:
        return
    for fence in fences:
        try:
            await delete_if_value(redis, fence.fence_key, fence.fence_value)
        except Exception as exc:
            logger.warning("Could not drop checkout fence %s: %s", fence.fence_key, exc)


async def live_run_id(session: AsyncSession, agent_slug: str, company_id: str) -> Optional[uuid.UUID]:
    """The run this agent is working in right now, or ``None``: its newest non-terminal run in the company.

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
        .order_by(LLCHeartbeatRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
