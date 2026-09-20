# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wires ``services.orphan_storage.delete_candidate()`` behind an approved cleanup request.

``orphan_storage.py`` deliberately "has no concept of who approved anything"
(its own docstring) -- this module is the caller #17038/#17039 said had that
job. A proposal is an ordinary approval-gate request
(``POST /approval-gates``, ``approval_type=destructive_action``) whose
``context`` names this action and the candidate:

    {"action": "orphan_storage_delete", "provider": "...", "candidate_id": "..."}

Approving it runs ``execute_orphan_storage_delete`` via the generic
``services.approval_execution`` registry -- ``delete_candidate()`` re-checks
orphan status and the grace period at THIS point, not at proposal time, so a
candidate whose record reappeared between proposal and approval is refused
rather than deleted. The result (deleted or not, and why) is never silent:
it lands as a comment on the approval itself, visible in the same inbox that
showed the proposal, and as a durable audit entry (#17038 rule 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action
from services.audit_logger import audit_log
from services.orphan_storage import delete_candidate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "orphan_storage_delete"


async def execute_orphan_storage_delete(approval: "Approval", session: "AsyncSession") -> None:
    """Delete the candidate an approved gate named, and record what happened."""
    context = approval.context or {}
    provider = context.get("provider")
    candidate_id = context.get("candidate_id")
    if not provider or not candidate_id:
        # #17141: raise rather than log-and-return. approval_execution's
        # dispatcher is the sole owner of failure recording -- returning
        # quietly here would leave the approval reading APPROVED with
        # nothing durable, exactly the hole that issue closes. Raising lets
        # the dispatcher's own except-and-record path catch this the same
        # way it catches any other handler failure, with no separate
        # recording logic to keep in sync here.
        raise ValueError(f"approval {approval.id} is missing provider/candidate_id in its action context")

    result = await delete_candidate(provider, candidate_id)

    body = f"Orphan-storage cleanup {'deleted' if result.deleted else 'did NOT delete'} {provider}:{candidate_id}"
    if result.reason:
        body += f" ({result.reason})"
    session.add(
        ApprovalComment(
            approval_id=approval.id,
            author="system",
            author_type="system",
            body=body,
        )
    )
    await session.commit()

    await audit_log(
        "orphan_storage.delete",
        result="success" if result.deleted else "failed",
        user_id=approval.decided_by_user,
        resource=f"{provider}:{candidate_id}",
        details={"approval_id": str(approval.id), "reason": result.reason},
    )


def register() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(ACTION, execute_orphan_storage_delete)


__all__ = ["ACTION", "execute_orphan_storage_delete", "register"]
