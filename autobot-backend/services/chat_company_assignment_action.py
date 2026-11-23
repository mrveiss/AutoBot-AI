# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an APPROVED proposal to assign a legacy Company OS chat to its company (#16905, #17038, #21997).

The proposal (``services/chat_company_proposals.py``) is an ordinary approval gate whose context names this
action, the chat and the company the backfill's classifier confirmed::

    {"action": "chat_company_assignment", "session_id": "...", "company_id": "..."}

Approving it writes the company through ``assign_company_audited`` -- the same compare-and-set between an
``attempted`` and an outcome audit row that ``POST /chat/sessions/{id}/company`` uses -- so a chat that was tagged
in the meantime is refused (the route's 409) and the proposal is recorded as stale instead of moving the chat.
Rejecting writes nothing. Only an admin may approve (a person, never a service), and the approver is the audit
actor.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from autobot_shared.logging_manager import get_logger
from models.approval import ApprovalComment, ApprovalStatus
from services.approval_execution import register_post_approval_action, verified_decider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "chat_company_assignment"

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.chat_company_proposals"

#: Where the audit row says the assignment came from (there is no request, so no client address).
_APPROVAL_QUEUE = "approval-queue"


async def _note(approval: "Approval", session: "AsyncSession", body: str) -> None:
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


def _actor(approval: "Approval", decider: uuid.UUID) -> dict:
    """Who assigned, for the audit row: the verified approver, never the proposer."""
    return {"user_id": str(decider), "username": str(approval.decided_by_user or decider), "ip": _APPROVAL_QUEUE}


def _target(approval: "Approval") -> tuple[str, str]:
    """The chat and company the approval names, or raise: nothing is taken from anywhere else."""
    ctx = approval.context or {}
    if ctx.get("action") != ACTION or approval.status != ApprovalStatus.APPROVED.value:
        raise ValueError(f"approval {approval.id} is not an approved {ACTION} proposal; the assignment is refused")
    session_id, company = ctx.get("session_id"), ctx.get("company_id")
    if not session_id or not company:
        raise ValueError(f"approval {approval.id} is missing session_id or company_id in its action context")
    return str(session_id), str(uuid.UUID(str(company)))


async def _stale_reason(manager, session_id: str, company: str) -> str | None:
    """Why the assignment no longer applies (the route's 404/409 cases), or ``None`` when it still does."""
    from security.session_company import company_exists

    if await manager.get_session(session_id) is None:
        return "the chat no longer exists"
    if await manager.get_session_company(session_id):
        return "the chat already has a company"
    if not await company_exists(uuid.UUID(company)):
        return "the company no longer exists"
    return None


async def execute_chat_company_assignment(approval: "Approval", session: "AsyncSession") -> None:
    """Assign the approved chat once, audited; a stale proposal is recorded, never forced."""
    from chat_history import ChatHistoryManager
    from security.session_share_audit import assign_company_audited

    session_id, company = _target(approval)
    decider = verified_decider(approval)
    if decider is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the assignment is refused")
    manager = ChatHistoryManager()
    stale = await _stale_reason(manager, session_id, company)
    if stale is None:
        # A lost race is still refused by the compare-and-set, and its outcome row is ``failed``.
        stale = (
            None
            if await assign_company_audited(manager, session_id, company, _actor(approval, decider))
            else ("the chat was assigned while this was being applied")
        )
    if stale:
        logger.info("Chat company proposal %s is stale: %s", approval.id, stale)
        await _note(approval, session, f"Stale: {stale}; chat {session_id} was left unchanged.")
        return
    await _note(approval, session, f"Chat {session_id} assigned to company {company} (audited).")
    from api.session_events import publish_session_updated

    await publish_session_updated(session_id, {"companyId": company})


def register_chat_company_assignment_action() -> None:
    """Idempotent. Server-only and admin-only: the chat and company are the proposer's to name, never a caller's."""
    register_post_approval_action(
        ACTION, execute_chat_company_assignment, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )


__all__ = ["ACTION", "PROPOSED_BY", "execute_chat_company_assignment", "register_chat_company_assignment_action"]
