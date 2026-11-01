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

from ..models.enums import WorkItemStatus
from ..models.work_item import LLCWorkItem


def is_own_task(item: LLCWorkItem, acting_user: Optional[uuid.UUID]) -> bool:
    """Whether *acting_user*, the verified caller, created this task or is assigned it."""
    return acting_user is not None and acting_user in (item.created_by_user_id, item.assignee_user_id)


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
