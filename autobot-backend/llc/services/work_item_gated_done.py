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
from .authz import is_company_member
from .work_item_own_task import InvalidTransition

_NO_NODE = "this agent has no org node, so a gated item cannot be handed to review"
_NOT_A_PERSON = "this credential is neither a person nor the agent holding the item"


class ReviewRefused(InvalidTransition):
    """A handoff to review that was refused; ``reason`` is a code a caller can branch on without parsing the text.

    It is an ``InvalidTransition``, so every caller that catches that keeps working (#21591).
    """

    NO_SERVICE = "no_handoff_service"
    NO_REVIEWER = "no_reviewer"
    NOT_A_MEMBER = "reviewer_not_a_member"
    NOT_THE_HOLDER = "not_the_holder"

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class DoneGate:
    """What a caller of ``transition_status`` brings to a move to done: the gate's services and who is finishing.

    ``agent_id`` is the agent node the credential resolves to; ``is_agent`` says the credential names an agent even
    when it has no node. ``local_person`` names the single local user when authentication is disabled: a person
    without a user id, who is never gated.
    """

    review_gate_svc: Optional[Any] = None
    handoff_svc: Optional[Any] = None
    agent_id: Optional[str] = None
    is_agent: bool = False
    local_person: Optional[str] = None

    def finish_args(self, acting_user: Optional[uuid.UUID]) -> Dict[str, Any]:
        """The keyword arguments of ``WorkItemService.transition_to_done`` for this caller."""
        return {
            "acting_user": acting_user,
            "actor_user_id": str(acting_user) if acting_user is not None else self.local_person,
            "actor_agent_id": self.agent_id,
            "review_gate_svc": self.review_gate_svc,
            "handoff_svc": self.handoff_svc,
            "is_agent": self.is_agent,
        }


def default_gate() -> DoneGate:
    """The gate a move to done gets when its caller brings none: the shared services, no agent, no person."""
    from .accessors import done_gate_for  # lazy: the accessors import the services that import this module

    return done_gate_for()


def item_reviewer(item: LLCWorkItem) -> Optional[str]:
    """Who reviews a finished item: its own reviewer, else the person who created it (#21503)."""
    found = item.reviewer_user_id or item.created_by_user_id
    return str(found) if found else None


async def hand_off_for_review(
    handoff_svc: Optional[Any], session: AsyncSession, item: LLCWorkItem, company_id: str, agent_id: str
) -> LLCWorkItem:
    """Move the item to review through ``HandoffService.agent_to_human``, naming the arguments it declares.

    The gate blocks the agent's done, so the item must go to a current member of the company: with no handoff
    service, no reviewer, a reviewer who is not a member, or an agent that does not hold the item the transition
    is refused, never completed past the gate.
    """
    from .handoff import HandoffNotAllowed  # lazy: the handoff module pulls in llc.kb (#13057)

    work_item_id = str(item.id)
    refusal = f"Work item {work_item_id} requires human review before it can be marked done. "
    if handoff_svc is None:
        raise ReviewRefused(refusal + "No HandoffService available to initiate handoff.", ReviewRefused.NO_SERVICE)
    reviewer = item_reviewer(item)
    if not reviewer:
        raise ReviewRefused(
            refusal + "A reviewer is required to initiate the handoff: it has none and no creator.",
            ReviewRefused.NO_REVIEWER,
        )
    if not await is_company_member(session, company_id, reviewer):
        raise ReviewRefused(
            refusal + "The item's reviewer or creator is not a member of the company.", ReviewRefused.NOT_A_MEMBER
        )
    try:
        return await handoff_svc.agent_to_human(
            session, work_item_id, agent_id=agent_id, reviewer_user_id=reviewer, company_id=company_id
        )
    except HandoffNotAllowed as exc:
        raise ReviewRefused(str(exc), ReviewRefused.NOT_THE_HOLDER) from exc


async def review_outcome(
    session: AsyncSession,
    item: LLCWorkItem,
    company_id: str,
    gate: DoneGate,
    who: tuple,
    acting_user: Optional[uuid.UUID],
) -> Optional[LLCWorkItem]:
    """The item in review when the gate takes this finish, ``None`` when the finish may go ahead.

    A person, or a board override, is never gated. Anyone else finishing a gated type is refused unless
    it is the agent holding the item, whose finish becomes a handoff. A caller with no gate is refused.
    *who* is (agent id, user id, board override); a user id or *acting_user* makes the caller a person.
    """
    _agent, user_id, is_board_override = who
    if user_id is not None or acting_user is not None or is_board_override:
        return None
    if gate.review_gate_svc is None:
        raise InvalidTransition(f"Work item {item.id} cannot be marked done: no review gate was supplied.")
    requires, _role = await gate.review_gate_svc.requires_review(session, company_id, WorkItemType(item.type))
    if not requires:
        return None
    if gate.agent_id is None:
        why = _NO_NODE if gate.is_agent else _NOT_A_PERSON
        raise InvalidTransition(f"Work item {item.id} requires human review before it can be marked done: {why}.")
    return await hand_off_for_review(gate.handoff_svc, session, item, company_id, gate.agent_id)
