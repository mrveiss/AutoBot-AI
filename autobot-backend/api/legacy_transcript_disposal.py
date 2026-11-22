# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a session delete may do to the session's legacy transcript: nothing (#18293, #17038).

``DELETE /chat/sessions/{id}`` used to remove the transcript before it knew the
session existed, and ``validate_session_ownership`` hands an ownerless session to
whoever asks (``reason="legacy_migration"``). A later attempt allowed removal for
the session's "verified owner"; review showed that owner can be manufactured two
ways -- creating a session over a legacy-only id, or a claim followed by a save
that stamps ``metadata.owner`` on the file. Ownership of a legacy transcript cannot
be proven from current state, so the rule is now:

* the chat session is deleted FIRST; a session that does not exist in
  ``chat_sessions`` is a 404 and nothing else is touched
  (:func:`delete_session_or_refer`);
* a session delete NEVER removes a legacy transcript. When one exists it stays on
  disk and a #17038 proposal records who asked (:func:`propose_transcript_disposal`);
  only a human's approval removes it (``services/legacy_transcript_disposal_action.py``);
* creating a session over a legacy-only id is refused with 409
  (``api/chat_sessions._reject_session_id_collision``).
"""

from __future__ import annotations

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from chat_history.legacy_transcripts import legacy_transcript_file
from services.legacy_transcript_disposal_action import ACTION, register_disposal_action

logger = get_logger(__name__)

# Registered at import, like api/admin_orphan_storage.py: the handler must be in
# place before any approve() can reach a proposal this module raised.
register_disposal_action()


async def _pending_proposal_id(db, session_id: str) -> str | None:
    from models.approval import Approval, ApprovalStatus

    query = select(Approval.id).where(
        Approval.status == ApprovalStatus.PENDING.value,
        Approval.context["action"].astext == ACTION,
        Approval.context["session_id"].astext == session_id,
    )
    found = (await db.execute(query)).scalars().first()
    return str(found) if found else None


async def propose_transcript_disposal(session_id: str, requested_by: str | None, why: str) -> str:
    """Raise (or reuse the pending) #17038 proposal to remove one legacy transcript."""
    from models.approval import ApprovalType
    from services.approval_gate_service import ApprovalGateService
    from user_management.database import get_async_session_factory

    async with get_async_session_factory()() as db:
        existing = await _pending_proposal_id(db, session_id)
        if existing:
            return existing
        approval = await ApprovalGateService(db).create_approval(
            title=f"Remove legacy chat transcript: {session_id}",
            approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
            description=why,
            requested_by_agent=requested_by,
            context={"action": ACTION, "session_id": session_id, "requested_by": requested_by},
        )
    return str(approval.id)


async def _refer(session_id: str, requested_by: str | None, why: str) -> str | None:
    """Propose disposal; a failure to propose leaves the file and is reported, never raised."""
    try:
        return await propose_transcript_disposal(session_id, requested_by, why)
    except Exception as exc:
        logger.error("Could not record a #17038 proposal for session %s's transcript: %s", session_id, exc)
        return None


async def dispose_session_transcript(session_id: str, *, requested_by: str | None) -> dict:
    """Never remove: keep the session's legacy transcript and propose its disposal (#17038)."""
    if legacy_transcript_file(session_id) is None:
        return {"transcript_deleted": False, "proposal_id": None, "error": None}
    why = "The chat session was deleted; its legacy transcript was kept for review."
    proposal_id = await _refer(session_id, requested_by, why)
    error = None if proposal_id else "the transcript was kept, but its review proposal could not be recorded"
    return {"transcript_deleted": False, "proposal_id": proposal_id, "error": error}


async def delete_session_or_refer(chat_history_manager, session_id: str, requested_by: str | None) -> None:
    """Delete the chat session, or raise 404 -- referring a legacy-only transcript for review."""
    from exceptions import get_exceptions_lazy

    if await chat_history_manager.delete_session(session_id):
        return
    message = f"Session {session_id} not found"
    if legacy_transcript_file(session_id) is not None:
        why = "Delete requested for a session that exists only as a legacy transcript."
        if proposal_id := await _refer(session_id, requested_by, why):
            message += f"; its legacy transcript was referred for review (approval {proposal_id})"
    resource_not_found = get_exceptions_lazy()[2]
    raise resource_not_found(message)
