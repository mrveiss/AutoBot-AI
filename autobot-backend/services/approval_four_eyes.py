# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Four eyes on an admin's proposal that rewrites stored data (#19997, #20030, #17038).

A proposer records itself as ``requested_by_agent="<action prefix>:<user id>"``. The rule itself is
``autobot_shared.approval_four_eyes``; this supplies who is eligible here, the platform's active admins.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from autobot_shared.approval_four_eyes import four_eyes_self_approval, requester_id
from services.approval_execution import verified_decider
from user_management.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval


async def _platform_admin_ids(session: "AsyncSession") -> set[uuid.UUID]:
    """The active platform admins, locked until the decision commits so none can leave after the check."""
    query = select(User.id).filter_by(is_platform_admin=True, is_active=True, deleted_at=None).with_for_update()
    return set((await session.execute(query)).scalars().all())


async def is_self_approval(approval: "Approval", session: "AsyncSession", *, what: str) -> bool:
    """True for a flagged self-approval by the only admin; raises when the decider may not decide."""
    decider, requester = verified_decider(approval), requester_id(approval.requested_by_agent)
    if decider is None or requester is None:
        raise ValueError(f"{what} needs a verified decider and a requester that can be identified")
    eligible = await _platform_admin_ids(session)
    return four_eyes_self_approval(decider, requester, eligible, what=what, who="admin")
