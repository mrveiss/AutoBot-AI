# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A person moves their own task freely (#20508, maintainer decision).

Their own means they created it or it is assigned to them. Every other task, and every agent,
keeps the transition rules in ``work_item_service``.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value

from ..models.enums import AssigneeType, WorkItemStatus
from ..models.work_item import LLCWorkItem

logger = get_logger(__name__)

_CHECKOUT_KEY_PREFIX = "llc:checkout:"
_PENDING_KEY = "llc_checkout_fence_pending_release"
_HOOKED_KEY = "llc_checkout_fence_release_hooked"
#: Strong references so a release task is not collected before it runs.
_release_tasks: set["asyncio.Task[None]"] = set()


@dataclass(frozen=True)
class _PendingRelease:
    item_id: uuid.UUID
    holder: str
    transaction: Optional[SessionTransaction]


def _past_its_reviewer(item: LLCWorkItem, acting_user: uuid.UUID, new_status: Optional[WorkItemStatus]) -> bool:
    """An item in review, with a reviewer who is someone else, is not finished by moving it to done."""
    reviewer = item.reviewer_user_id
    return (
        new_status == WorkItemStatus.DONE
        and item.status == WorkItemStatus.IN_REVIEW
        and reviewer is not None
        and reviewer != acting_user
    )


class InvalidTransition(Exception):
    """Raised when a status transition is not permitted."""


def refuse_past_reviewer(item: LLCWorkItem, acting_user: Optional[uuid.UUID], new_status: WorkItemStatus) -> None:
    """A person can't finish a task waiting on someone else's review; that reviewer decides (#20508).

    Applies to people only: *acting_user* is None for any other credential, which keeps its own rules.
    """
    if acting_user is not None and _past_its_reviewer(item, acting_user, new_status):
        raise InvalidTransition("This task is waiting on its reviewer, who decides whether it is done")


def is_own_task(
    item: LLCWorkItem, acting_user: Optional[uuid.UUID], new_status: Optional[WorkItemStatus] = None
) -> bool:
    """Whether *acting_user*, the verified caller, may move this task freely.

    They created it or are assigned it -- except that moving it from review to done past a reviewer
    who is someone else keeps the normal rules (#20508). A blocked task with blockers stays free.
    """
    if acting_user is None or acting_user not in (item.created_by_user_id, item.assignee_user_id):
        return False
    return not _past_its_reviewer(item, acting_user, new_status)


def stamp_status(item: LLCWorkItem, new_status: WorkItemStatus, now: datetime, *, own: bool = False) -> None:
    """Set the status and its timestamps; a move by the owner also clears what no longer holds."""
    item.status = new_status
    if own:
        item.completed_at = None
        item.cancelled_at = None
        if new_status != WorkItemStatus.IN_PROGRESS:  # a run holding it no longer has it
            item.checkout_run_id = None
            item.checkout_locked_at = None
    if new_status == WorkItemStatus.IN_PROGRESS and item.started_at is None:
        item.started_at = now
    elif new_status == WorkItemStatus.DONE:
        item.completed_at = now
        item.checkout_run_id = None
        item.checkout_locked_at = None
    elif new_status == WorkItemStatus.CANCELLED:
        item.cancelled_at = now


def other_checkout_holder(item: LLCWorkItem, agent_id: str) -> Optional[str]:
    """Who holds *item* instead of agent *agent_id*, read under the row lock: another agent or a person.

    A person's claim leaves ``checkout_run_id`` empty, so the claim stamp is what an agent checkout must respect.
    """
    if item.checkout_run_id is not None and str(item.assignee_agent_id) != agent_id:
        return f"agent {item.assignee_agent_id}"
    if item.assignee_user_id is not None and item.checkout_locked_at is not None:
        return f"user {item.assignee_user_id}"
    return None


def claim_conflict_holder(item: LLCWorkItem, user_id: str) -> Optional[str]:
    """Who holds *item* instead of person *user_id*, read under the row lock: a live agent or another person."""
    if item.assignee_agent_id is not None and (holder := other_checkout_holder(item, user_id)):
        return holder if holder.startswith("agent ") else None
    if item.assignee_user_id is not None and str(item.assignee_user_id) != user_id:
        return f"user {item.assignee_user_id}"
    return None


def stamp_agent_checkout(item: LLCWorkItem, agent_id: str, run_id: Optional[str], work_intent: Optional[str]) -> None:
    """Record an agent's checkout on the locked row and start the item if it was waiting."""
    now = datetime.now(timezone.utc)
    item.checkout_run_id = run_id or str(uuid.uuid4())
    item.checkout_locked_at = now
    item.assignee_agent_id = uuid.UUID(agent_id)
    # Single-assignee invariant (#10532): `update()` enforced it, `checkout` did not (#15964).
    item.assignee_user_id = None
    item.assignee_type = AssigneeType.AGENT.value
    # GH#9532 -- persist intent for audit; clearing it when work_intent is absent is deliberate.
    item.checkout_intent = work_intent
    item.version += 1
    if item.status in (WorkItemStatus.BACKLOG, WorkItemStatus.READY):
        item.status = WorkItemStatus.IN_PROGRESS
        item.started_at = item.started_at or now


_FENCE_GENERATION_SEP = "#"


def checkout_fence_value(agent_id: str, run_id: Optional[str]) -> str:
    """The fence value of one agent checkout: the agent id tagged with the checkout generation (``checkout_run_id``).

    The tag lets a release deferred from an earlier transition compare-and-delete only its own generation, so it
    cannot drop the fence the same agent took by checking out again.
    """
    if _FENCE_GENERATION_SEP in agent_id:
        raise ValueError(
            f"agent id {agent_id!r} must not contain {_FENCE_GENERATION_SEP!r}: it separates the fence generation"
        )
    return f"{agent_id}{_FENCE_GENERATION_SEP}{run_id}" if run_id else agent_id


async def drop_fence(redis: Any, key: str, value: str, acquired: bool) -> None:
    """Take back a fence THIS call acquired, while it still names *value*; a fence it did not take is left alone."""
    if acquired:
        await delete_if_value(redis, key, value)


def fence_agent(value: str) -> str:
    """The agent id a fence value names, whatever generation it carries."""
    return value.split(_FENCE_GENERATION_SEP, 1)[0]


def _checkout_holder(item: LLCWorkItem) -> Optional[str]:
    """The item's fence value: ``user:<id>`` for a claim, the generation-tagged agent id for a checkout."""
    if item.assignee_user_id:
        return f"user:{item.assignee_user_id}"
    if not item.assignee_agent_id:
        return None
    return checkout_fence_value(str(item.assignee_agent_id), item.checkout_run_id)


async def _delete_fence(item_id: uuid.UUID, holder: str) -> None:
    """Delete the fence while it still names *holder*. A Redis failure is logged: the fence expires on its TTL."""
    try:
        redis = await get_async_redis_client()
        if redis is not None:
            await delete_if_value(redis, f"{_CHECKOUT_KEY_PREFIX}{item_id}", holder)
    except Exception:
        logger.warning("Checkout fence of work item %s was not released; it expires on its TTL", item_id, exc_info=True)


def _spawn_release(item_id: uuid.UUID, holder: str) -> None:
    try:
        task = asyncio.get_running_loop().create_task(_delete_fence(item_id, holder))
    except RuntimeError:
        logger.warning("No event loop to release the checkout fence of work item %s; it expires on its TTL", item_id)
        return
    _release_tasks.add(task)
    task.add_done_callback(_release_tasks.discard)


def _release_committed(sync: Session) -> None:
    """``after_commit``: the transition is durable, so drop each queued fence. Also fires on a SAVEPOINT release."""
    if sync.in_nested_transaction():
        return
    for pending in sync.info.pop(_PENDING_KEY, []):
        _spawn_release(pending.item_id, pending.holder)


def _forget_undone(sync: Session, previous_transaction: SessionTransaction) -> None:
    """Drop the releases whose transition this rollback (outer or SAVEPOINT) undid: the row still names the holder."""
    # Imported here: event_wake reaches the accessors through dispatch_gate, and the accessors import this module.
    from ..scheduler.event_wake import within_transaction

    pending = sync.info.get(_PENDING_KEY, [])
    pending[:] = [p for p in pending if not within_transaction(p.transaction, previous_transaction)]


def _release_after_commit(session: AsyncSession, item_id: uuid.UUID, holder: str) -> None:
    """Queue the fence release on *session*; a commit sends it, a rollback drops it.

    An object that is not a real SQLAlchemy session has no commit to follow, so it is released at once.
    """
    sync = getattr(session, "sync_session", None)
    if not isinstance(sync, Session):
        _spawn_release(item_id, holder)
        return
    if not sync.info.get(_HOOKED_KEY):
        event.listen(sync, "after_commit", _release_committed)
        event.listen(sync, "after_soft_rollback", _forget_undone)
        sync.info[_HOOKED_KEY] = True
    txn = sync.get_nested_transaction() or sync.get_transaction()
    sync.info.setdefault(_PENDING_KEY, []).append(_PendingRelease(item_id, holder, txn))


def stamp_and_release(
    session: AsyncSession, item: LLCWorkItem, new_status: WorkItemStatus, now: datetime, *, own: bool = False
) -> None:
    """:func:`stamp_status`, and drop the checkout fence with the checkout it clears, while it names the holder.

    A fence left behind refuses every other checkout until it expires. It is released after the caller's commit:
    a rollback keeps the row naming the holder, so the fence must still stand. A failed release is logged and
    the fence expires on its TTL, so it can never fail the transition.
    """
    held = item.checkout_locked_at is not None
    holder = _checkout_holder(item)
    stamp_status(item, new_status, now, own=own)
    if held and holder is not None and item.checkout_locked_at is None:
        _release_after_commit(session, item.id, holder)
