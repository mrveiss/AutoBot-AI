# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The review-gated done path of ``transition_to_done``: an agent's finish becomes a handoff (#21457)."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.work_item import LLCWorkItem
from .work_item_own_task import InvalidTransition


async def hand_off_for_review(
    handoff_svc: Optional[Any],
    session: AsyncSession,
    work_item_id: str,
    company_id: str,
    agent_id: str,
    reviewer_user_id: Optional[str],
) -> LLCWorkItem:
    """Move the item to review through ``HandoffService.agent_to_human``, naming the arguments it declares.

    The gate blocks the agent's done, so the item must go to someone: with no handoff service or no reviewer the
    transition is refused, never completed past the gate.
    """
    if handoff_svc is None:
        raise InvalidTransition(
            f"Work item {work_item_id} requires human review before it can be marked done. "
            "No HandoffService available to initiate handoff."
        )
    if not reviewer_user_id:
        raise InvalidTransition(
            f"Work item {work_item_id} requires human review before it can be marked done. "
            "A reviewer is required to initiate the handoff."
        )
    return await handoff_svc.agent_to_human(
        session, work_item_id, agent_id=agent_id, reviewer_user_id=reviewer_user_id, company_id=company_id
    )
