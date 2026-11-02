# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Four eyes on an admin's proposal that rewrites stored data (#19997, #20030, #17038).

A proposer records itself as ``requested_by_agent="<action prefix>:<user id>"``. The decider must be a
verified person other than the proposer; the only platform admin may decide their own, and it is flagged.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from services.approval_execution import verified_decider
from user_management.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval


def requester_id(approval: "Approval") -> uuid.UUID | None:
    """The admin who proposed it, from ``requested_by_agent``; None when it names nobody."""
    try:
        return uuid.UUID(str(approval.requested_by_agent).rsplit(":", 1)[-1])
    except ValueError:
        return None


async def _platform_admin_count(session: "AsyncSession") -> int:
    query = select(func.count()).select_from(User).filter_by(is_platform_admin=True, is_active=True, deleted_at=None)
    rows = await session.execute(query)
    return int(rows.scalar_one())


async def is_self_approval(approval: "Approval", session: "AsyncSession") -> bool:
    """True for a flagged self-approval by the only admin; raises when the decider may not decide."""
    decider, requester = verified_decider(approval), requester_id(approval)
    if decider is None or requester is None:
        raise ValueError("this needs a verified decider and a requester that can be identified")
    if decider != requester:
        return False
    if await _platform_admin_count(session) >= 2:
        raise ValueError("this needs a different admin than the one who proposed it")
    return True
