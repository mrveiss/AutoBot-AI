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

from typing import TYPE_CHECKING, Any

from models.approval import ApprovalComment, ApprovalType
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval


def cleanup_proposal(current_user: dict, *, title: str, description: str, context: dict[str, Any]) -> dict[str, Any]:
    """Keyword arguments for ``ApprovalGateService.create_approval``: a PENDING destructive-action request."""
    return {
        "title": title,
        "approval_type": ApprovalType.DESTRUCTIVE_ACTION.value,
        "description": description,
        "requested_by_agent": current_user.get("username"),
        "context": context,
    }


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
    await audit_log(
        operation,
        result="success" if done else "failed",
        user_id=approval.decided_by_user,
        resource=resource,
        details={"approval_id": str(approval.id), "reason": reason},
    )
