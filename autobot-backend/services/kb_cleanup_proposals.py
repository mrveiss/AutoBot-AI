# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared plumbing for knowledge-base cleanups that stored data may only receive after a human approves (#17038).

A cleanup is never an admin-gated action. The route PROPOSES it as an approval-gate request
(``destructive_action``) and the registered post-approval handler performs it afterwards, so an agent or a
route that deletes or rewrites stored data without that decision cannot be written with these helpers. Each
proposer module still calls ``create_approval`` itself (the registry guard checks it does); what is shared
here is what every such proposal and every handler outcome has in common.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from autobot_shared.logging_manager import get_logger
from models.approval import Approval, ApprovalComment, ApprovalStatus, ApprovalType
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.approval_gate_service import ApprovalGateService

logger = get_logger(__name__)

_NOT_RECORDED = "The proposal could not be audit-logged, so it was not created"


def cleanup_proposal(
    current_user: dict, *, title: str, description: str, context: dict[str, Any], approval_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Keyword arguments for ``ApprovalGateService.create_approval``: a PENDING destructive-action request."""
    return {
        "title": title,
        "approval_type": ApprovalType.DESTRUCTIVE_ACTION.value,
        "description": description,
        "requested_by_agent": current_user.get("username"),
        "context": context,
        **({"approval_id": approval_id} if approval_id else {}),
    }


async def find_pending_proposal(service: "ApprovalGateService", action: str, key: str, value: str) -> "Approval | None":
    """The still-pending proposal of *action* for the same target (context[key] == value), if any."""
    found = await service.list_approvals(
        status=ApprovalStatus.PENDING.value,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        extra_where=(Approval.context["action"].astext == action, Approval.context[key].astext == value),
        limit=1,
    )
    return found[0] if found else None


async def create_proposal_once(
    service: "ApprovalGateService",
    action: str,
    key: str,
    value: str,
    create: Callable[[uuid.UUID], Awaitable["Approval"]],
    *,
    current_user: dict,
    resource: str,
) -> "Approval":
    """The pending proposal for the target, creating it with ``create(approval_id)`` when none is open.

    The read-then-create can race; the partial unique index per action (``uq_approvals_pending_*``, #20992)
    makes the loser's insert fail. The audit store commits on its own (it does not share the approval's
    transaction), so the loser's creation row cannot be rolled back with its insert: the loser instead leaves a
    ``proposal_lost_race`` row naming both ids, and returns the winner's proposal (#17038).
    """
    if (existing := await find_pending_proposal(service, action, key, value)) is not None:
        return existing
    approval_id = uuid.uuid4()
    try:
        return await create(approval_id)
    except IntegrityError:  # a concurrent request created it first
        await service.session.rollback()
        if (winner := await find_pending_proposal(service, action, key, value)) is None:
            raise
        await _record_lost_race(approval_id, winner.id, current_user, resource)
        return winner


async def _record_lost_race(lost_id: uuid.UUID, winner_id: uuid.UUID, current_user: dict, resource: str) -> None:
    """Durable row saying the creation row naming *lost_id* never became an approval; *winner_id* did."""
    try:
        written = await audit_log(
            AuditAction.CLEANUP_PROPOSAL_LOST_RACE,
            result="success",
            user_id=current_user.get("username"),
            resource=resource,
            details={"approval_id": str(lost_id), "winner_approval_id": str(winner_id)},
            durable=True,
        )
    except Exception:
        logger.exception("Cleanup proposal %s: the lost-race audit write raised", lost_id)
        written = False
    if not written:
        logger.error("Cleanup proposal %s lost the race to %s and could not be annotated", lost_id, winner_id)


async def record_cleanup_proposed(approval_id: uuid.UUID, current_user: dict, *, operation: str, resource: str) -> None:
    """The durable audit row for a proposal, written BEFORE the approval exists (#17038).

    No row means no proposal: a failed or refused write is a 503 and nothing is created.
    """
    try:
        written = await audit_log(
            operation,
            result="success",
            user_id=current_user.get("username"),
            resource=resource,
            details={"approval_id": str(approval_id)},
            durable=True,
        )
    except Exception:
        logger.exception("Cleanup proposal %s: the audit write raised", approval_id)
        written = False
    if not written:
        logger.error("Cleanup proposal %s for %s: not audit-logged, so not created", approval_id, resource)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_RECORDED)


def require_context(approval: "Approval", *keys: str) -> list[Any]:
    """The named context values; raises when one is missing so the dispatcher records the failure (#17141)."""
    context = approval.context or {}
    values = [context.get(key) for key in keys]
    if not all(values):
        raise ValueError(f"approval {approval.id} is missing {', '.join(keys)} in its action context")
    return values


async def record_cleanup_outcome(
    approval: "Approval",
    session: "AsyncSession",
    *,
    operation: str,
    done: bool,
    resource: str,
    summary: str,
    reason: str | None,
) -> None:
    """Leave the outcome (done or not, and why) as a comment on the approval and as a durable audit entry."""
    body = f"{summary} {'done' if done else 'did NOT run'} for {resource}"
    session.add(
        ApprovalComment(
            approval_id=approval.id,
            author="system",
            author_type="system",
            body=f"{body} ({reason})" if reason else body,
        )
    )
    await session.commit()
    await _audit_outcome(approval, session, operation, done, resource, reason)


async def _audit_outcome(
    approval: "Approval", session: "AsyncSession", operation: str, done: bool, resource: str, reason: str | None
) -> None:
    """Write the outcome audit row; a failure is logged and shown on the approval, never silent."""
    try:
        written = await audit_log(
            operation,
            result="success" if done else "failed",
            user_id=approval.decided_by_user,
            resource=resource,
            details={"approval_id": str(approval.id), "reason": reason},
            durable=True,
        )
    except Exception:
        logger.exception("Cleanup outcome %s: the audit write raised", approval.id)
        written = False
    if written:
        return
    logger.error("Cleanup outcome for approval %s (%s) was NOT audit-logged", approval.id, resource)
    session.add(
        ApprovalComment(
            approval_id=approval.id,
            author="system",
            author_type="system",
            body=f"WARNING: the audit entry for this outcome ({resource}) could not be written",
        )
    )
    await session.commit()
