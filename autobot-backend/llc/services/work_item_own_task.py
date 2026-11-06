# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A person moves their own task freely (#20508, maintainer decision).

Their own means they created it or it is assigned to them. Every other task, and every agent,
keeps the transition rules in ``work_item_service``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value

from ..models.enums import WorkItemStatus
from ..models.work_item import LLCWorkItem

_CHECKOUT_KEY_PREFIX = "llc:checkout:"


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


def _checkout_holder(item: LLCWorkItem) -> Optional[str]:
    """The value the item's checkout fence holds: ``user:<id>`` for a claim, the bare agent id for a checkout."""
    if item.assignee_user_id:
        return f"user:{item.assignee_user_id}"
    return str(item.assignee_agent_id) if item.assignee_agent_id else None


async def stamp_and_release(item: LLCWorkItem, new_status: WorkItemStatus, now: datetime, *, own: bool = False) -> None:
    """:func:`stamp_status`, and drop the checkout fence with the checkout it clears, while it names the holder.

    A fence left behind refuses every other checkout until it expires. It runs before the caller's commit; if that
    rolls back, the row still names the holder, and the row is what ``checkout`` refuses on.
    """
    held = item.checkout_locked_at is not None
    holder = _checkout_holder(item)
    stamp_status(item, new_status, now, own=own)
    if held and holder is not None and item.checkout_locked_at is None:
        redis = await get_async_redis_client()
        if redis is not None:
            await delete_if_value(redis, f"{_CHECKOUT_KEY_PREFIX}{item.id}", holder)
