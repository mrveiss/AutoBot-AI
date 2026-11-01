# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an APPROVED proposal to remove one deleted conversation file's bytes (#20234, #17038).

The proposal (``services/conversation_file_cleanup_proposals.py``) is an ordinary approval
gate whose context names this action and the file id -- never a path::

    {"action": "conversation_file_cleanup", "file_id": "...", "session_id": "..."}

Approving it runs :func:`execute_conversation_file_cleanup` through the generic
``services.approval_execution`` registry. The path is read from the file record and
re-validated against the store at removal time. The outcome lands as a comment on the
approval and as a durable audit entry (#17038 rule 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "conversation_file_cleanup"

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.conversation_file_cleanup_proposals"


async def execute_conversation_file_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove the bytes an approved gate named, and record what happened."""
    from conversation_file_cleanup import remove_approved_file
    from conversation_file_manager import get_conversation_file_manager

    file_id = (approval.context or {}).get("file_id")
    if not file_id:
        # #17141: raise, so the dispatcher records the failure durably.
        raise ValueError(f"approval {approval.id} is missing file_id in its action context")

    result = await remove_approved_file(await get_conversation_file_manager(), file_id)
    outcome = "removed" if result["removed"] else "did NOT remove"
    body = f"Conversation file cleanup {outcome} the bytes of file {file_id} ({result['size']} bytes)"
    if result["reason"]:
        body += f": {result['reason']}"
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await audit_log(
        "conversation_file.cleanup",
        result="success" if result["removed"] else "failed",
        user_id=approval.decided_by_user,
        resource=f"conversation_file:{file_id}",
        details={"approval_id": str(approval.id), "size": result["size"], "reason": result["reason"]},
    )


def register_conversation_file_cleanup_action() -> None:
    """Idempotent. Server-only: the file id is the proposer's to name, never a caller's."""
    register_post_approval_action(ACTION, execute_conversation_file_cleanup, proposed_by=PROPOSED_BY, server_only=True)


__all__ = ["ACTION", "PROPOSED_BY", "execute_conversation_file_cleanup", "register_conversation_file_cleanup_action"]
