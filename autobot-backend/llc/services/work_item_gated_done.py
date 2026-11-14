# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The review gate of the one done path: an agent's finish becomes a handoff (#21457, #21503)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import WorkItemType
from ..models.work_item import LLCWorkItem
from .handoff import HandoffNotAllowed
from .work_item_own_task import InvalidTransition


@dataclass(frozen=True)
class DoneGate:
    """What a caller of ``transition_status`` brings to a move to done: the gate's services and who is finishing.

    ``agent_id`` is the agent node the credential resolves to, or ``None`` for a caller that is no known agent.
    """

    review_gate_svc: Optional[Any] = None
    handoff_svc: Optional[Any] = None
    agent_id: Optional[str] = None
    reviewer_user_id: Optional[str] = None

    def finish_args(self, acting_user: Optional[uuid.UUID]) -> Dict[str, Any]:
        """The keyword arguments of ``WorkItemService.transition_to_done`` for this caller."""
        return {
            "acting_user": acting_user,
            "actor_user_id": str(acting_user) if acting_user is not None else None,
            "actor_agent_id": self.agent_id,
            "review_gate_svc": self.review_gate_svc,
            "handoff_svc": self.handoff_svc,
            "reviewer_user_id": self.reviewer_user_id,
        }


def default_reviewer(item: LLCWorkItem) -> Optional[str]:
    """Who reviews when the agent names no one: the item's reviewer, else the person who created it (#21503)."""
    found = item.reviewer_user_id or item.created_by_user_id
    return str(found) if found else None


async def hand_off_for_review(
    handoff_svc: Optional[Any],
    session: AsyncSession,
    item: LLCWorkItem,
    company_id: str,
    agent_id: str,
    reviewer_user_id: Optional[str],
) -> LLCWorkItem:
    """Move the item to review through ``HandoffService.agent_to_human``, naming the arguments it declares.

    The gate blocks the agent's done, so the item must go to someone: with no handoff service, no reviewer, or an
    agent that does not hold the item the transition is refused, never completed past the gate.
    """
    work_item_id = str(item.id)
    refusal = f"Work item {work_item_id} requires human review before it can be marked done. "
    if handoff_svc is None:
        raise InvalidTransition(refusal + "No HandoffService available to initiate handoff.")
    reviewer = reviewer_user_id or default_reviewer(item)
    if not reviewer:
        raise InvalidTransition(
            refusal + "A reviewer is required to initiate the handoff: the item names none and has no creator."
        )
    try:
        return await handoff_svc.agent_to_human(
            session, work_item_id, agent_id=agent_id, reviewer_user_id=reviewer, company_id=company_id
        )
    except HandoffNotAllowed as exc:
        raise InvalidTransition(str(exc)) from exc


async def review_outcome(
    session: AsyncSession,
    item: LLCWorkItem,
    company_id: str,
    gate: DoneGate,
    *,
    is_human: bool,
    is_board_override: bool,
) -> Optional[LLCWorkItem]:
    """The item in review when the gate takes this finish, ``None`` when the finish may go ahead.

    A person, or a board override, is never gated. Anyone else finishing a gated type is refused unless
    it is the agent holding the item, whose finish becomes a handoff.
    """
    if is_human or is_board_override or gate.review_gate_svc is None:
        return None
    requires, _role = await gate.review_gate_svc.requires_review(session, company_id, WorkItemType(item.type))
    if not requires:
        return None
    if gate.agent_id is None:
        raise InvalidTransition(
            f"Work item {item.id} requires human review before it can be marked done, "
            "and this credential is neither a person nor the agent holding it."
        )
    return await hand_off_for_review(gate.handoff_svc, session, item, company_id, gate.agent_id, gate.reviewer_user_id)
