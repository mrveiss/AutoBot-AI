# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an APPROVED proposal to remove one legacy transcript (#18293, #17038).

A session delete never removes a legacy transcript: whoever deletes, and however
their ownership was established, the file stays on disk and a proposal is raised
(``api/legacy_transcript_disposal.py``) -- an ordinary approval gate,
``approval_type=destructive_action``, whose context names this action and the
user who asked, so the approver sees who wants it gone::

    {"action": "legacy_transcript_delete", "session_id": "...", "requested_by": "..."}

Approving it runs :func:`execute_legacy_transcript_delete` through the generic
``services.approval_execution`` registry. The outcome is never silent: it lands
as a comment on the approval and as a durable audit entry (#17038 rule 3).
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
ACTION = "legacy_transcript_delete"

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.legacy_transcript_disposal"


async def execute_legacy_transcript_delete(approval: "Approval", session: "AsyncSession") -> None:
    """Remove the transcript an approved gate named, and record what happened."""
    from chat_history.legacy_transcripts import remove_legacy_transcript

    session_id = (approval.context or {}).get("session_id")
    if not session_id:
        # #17141: raise, so the dispatcher records the failure durably.
        raise ValueError(f"approval {approval.id} is missing session_id in its action context")

    result = await remove_legacy_transcript(session_id)
    outcome = "removed" if result["transcript_deleted"] else "did NOT remove"
    body = f"Legacy transcript cleanup {outcome} the transcript of session {session_id}"
    if result["error"]:
        body += " (refused or failed; the backend log has the reason)"
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await audit_log(
        "legacy_transcript.delete",
        result="success" if result["transcript_deleted"] else "failed",
        user_id=approval.decided_by_user,
        resource=f"legacy_transcript:{session_id}",
        details={"approval_id": str(approval.id), "refused_or_failed": bool(result["error"])},
    )


def register_disposal_action() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler."""
    register_post_approval_action(ACTION, execute_legacy_transcript_delete, proposed_by=PROPOSED_BY)


__all__ = ["ACTION", "PROPOSED_BY", "execute_legacy_transcript_delete", "register_disposal_action"]
