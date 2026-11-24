# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Files the legacy-CEO-chat backfill's findings as approval-gate proposals (#16905, #17038, #21997).

``chat_history.session_scope_backfill.plan_dry_run`` classifies every chat and writes nothing; each ``taggable``
chat (a legacy "CEO · <company id>" chat whose id names a real company) becomes one PENDING proposal here. A
proposal only asks. It writes no chat, cannot approve itself and never expires into approval; the assignment
happens only if a person approves it (``services/chat_company_assignment_action.py``), through the audited assign
path. A chat with a pending, rejected or revision-requested proposal is not proposed again, so a re-run adds
nothing and a denial stays one. Two concurrent runs are settled by the partial unique index
``uq_approvals_pending_chat_company`` (migration 20261124_123): the loser's ``IntegrityError`` reads as "already
proposed".
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from autobot_shared.logging_manager import get_logger
from models.approval import ApprovalStatus
from services.chat_company_assignment_action import ACTION, register_chat_company_assignment_action

logger = get_logger(__name__)

REQUESTED_BY = "chat-company-backfill"

# Registered at import, so the handler is in place before any approve() can reach a proposal raised here.
register_chat_company_assignment_action()

#: Proposal states that keep a chat from being proposed again.
_BLOCKING = (ApprovalStatus.PENDING.value, ApprovalStatus.REJECTED.value, ApprovalStatus.REVISION_REQUESTED.value)


async def _already_proposed(db) -> set[str]:
    """Chat ids with a proposal that must not be repeated. Plain columns only, any SQL dialect."""
    from models.approval import Approval, ApprovalType

    query = select(Approval.context).where(
        Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
        Approval.requested_by_agent == REQUESTED_BY,
        Approval.status.in_(_BLOCKING),
    )
    contexts = (await db.execute(query)).scalars().all()
    return {str(c["session_id"]) for c in contexts if c and c.get("action") == ACTION and c.get("session_id")}


async def _propose_one(db, service, candidate):
    """Create the proposal, or ``None`` when another run's pending one won the unique index."""
    from models.approval import ApprovalType

    try:
        return await service.create_approval(
            title=f"Assign legacy Company OS chat to its company: {candidate.name}",
            approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
            description=(
                f"The chat is named for company {candidate.company_id} and carries no company. "
                "Approving writes that company onto the chat; rejecting leaves it Unassigned."
            ),
            requested_by_agent=REQUESTED_BY,
            context={"action": ACTION, "session_id": candidate.session_id, "company_id": candidate.company_id},
        )
    except IntegrityError:
        await db.rollback()
        logger.info("Company proposal for chat %s already pending (raised concurrently)", candidate.session_id)
        return None


async def propose_assignments_for(db, candidates: list) -> list[str]:
    """One PENDING proposal per candidate with no pending or denied proposal; returns the new approval ids."""
    from services.approval_gate_service import ApprovalGateService

    seen = await _already_proposed(db)
    service = ApprovalGateService(db)
    created = []
    for candidate in candidates:
        if candidate.session_id in seen:
            continue
        approval = await _propose_one(db, service, candidate)
        if approval is not None:
            created.append(str(approval.id))
    return created


async def propose_company_assignments(chat_mgr) -> Dict[str, Any]:
    """Dry-run the backfill and raise proposals. Writes no chat; the plan's other buckets are only counted."""
    from chat_history.session_scope_backfill import plan_dry_run
    from user_management.database import get_async_session_factory

    plan = await plan_dry_run(chat_mgr)
    created: List[str] = []
    if plan.taggable:
        async with get_async_session_factory()() as db:
            created = await propose_assignments_for(db, plan.taggable)
    return {
        "scanned": plan.scanned,
        "taggable": len(plan.taggable),
        "proposed": created,
        "already_proposed": len(plan.taggable) - len(created),
        "already_tagged": len(plan.already_tagged),
        "unclassified": len(plan.unclassified),
    }
