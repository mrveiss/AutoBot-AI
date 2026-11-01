# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Turns due ``file_cleanup_queue`` entries into approval-gate proposals (#20234, #17038).

A proposal only asks. It deletes nothing, cannot approve itself, and never expires into
approval; a proposal nobody reviews stays pending in the Approvals inbox. A file with a
pending, rejected or revision-requested proposal is not proposed again: a denial is a person's
decision and stays one. An approved proposal whose removal failed, an expired one and a
withdrawn one leave the queue row unprocessed (the queue, not the proposal, records that the
bytes are gone), so the next sweep proposes that file again.
"""

from __future__ import annotations

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from models.approval import ApprovalStatus
from services.conversation_file_cleanup_action import ACTION, register_conversation_file_cleanup_action

logger = get_logger(__name__)

REQUESTED_BY = "conversation-file-cleanup"

# Registered at import, like api/legacy_transcript_disposal.py: the handler must be in
# place before any approve() can reach a proposal this module raised.
register_conversation_file_cleanup_action()


#: Proposal states that keep a file from being proposed again.
_BLOCKING = (ApprovalStatus.PENDING.value, ApprovalStatus.REJECTED.value, ApprovalStatus.REVISION_REQUESTED.value)


async def _already_proposed(db) -> set[str]:
    """File ids with a proposal that must not be repeated. Plain columns only, any SQL dialect."""
    from models.approval import Approval, ApprovalType

    query = select(Approval.context).where(
        Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
        Approval.requested_by_agent == REQUESTED_BY,
        Approval.status.in_(_BLOCKING),
    )
    contexts = (await db.execute(query)).scalars().all()
    return {str(c["file_id"]) for c in contexts if c and c.get("action") == ACTION and c.get("file_id")}


async def propose_cleanups_for(db, candidates: list[dict]) -> list[str]:
    """Create one PENDING proposal per candidate with no pending or denied proposal; returns the new ids."""
    from models.approval import ApprovalType
    from services.approval_gate_service import ApprovalGateService

    seen = await _already_proposed(db)
    service = ApprovalGateService(db)
    created = []
    for item in candidates:
        if item["file_id"] in seen:
            continue
        approval = await service.create_approval(
            title=f"Remove deleted conversation file: {item['original_filename']}",
            approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
            description=f"The file was deleted from its conversation; its {item['file_size']} bytes are still on disk.",
            requested_by_agent=REQUESTED_BY,
            context={"action": ACTION, "file_id": item["file_id"], "session_id": item["session_id"]},
        )
        created.append(str(approval.id))
    return created


async def propose_due_cleanups(manager) -> list[str]:
    """Sweep the queue and raise proposals. Never removes anything."""
    from conversation_file_cleanup import list_cleanup_candidates
    from user_management.database import get_async_session_factory

    candidates = await list_cleanup_candidates(manager)
    if not candidates:
        return []
    async with get_async_session_factory()() as db:
        return await propose_cleanups_for(db, candidates)


async def propose_due_cleanups_logged(manager) -> None:
    """Trigger for callers that must not fail on it: a failure is logged at error, the files stay."""
    try:
        created = await propose_due_cleanups(manager)
        if created:
            logger.info("Raised %d conversation file cleanup proposal(s) for review", len(created))
    except Exception as exc:
        logger.error("Could not raise conversation file cleanup proposals (files kept): %s", exc)
