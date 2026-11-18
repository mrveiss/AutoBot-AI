# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Proposes removing a deleted code source's run record; a human decides (#21417, #17038).

A proposal only asks. It deletes nothing, cannot approve itself, and never expires into approval: one
nobody reviews stays pending in the Approvals inbox. It names the source and the record
(``services/source_run_record_cleanup_action.py`` removes exactly that record once it is approved).
A source with a pending, rejected or revision-requested proposal is not proposed again -- a denial is a
person's decision and stays one.
"""

from __future__ import annotations

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from models.approval import ApprovalStatus
from services.source_run_record_cleanup_action import ACTION, register_source_run_record_cleanup_action

logger = get_logger(__name__)

REQUESTED_BY = "source-run-record-cleanup"

# Registered at import: the handler must be in place before any approve() can reach a proposal
# this module raised (as services/conversation_file_cleanup_proposals.py does).
register_source_run_record_cleanup_action()

#: Proposal states that keep a source from being proposed again.
_BLOCKING = (ApprovalStatus.PENDING.value, ApprovalStatus.REJECTED.value, ApprovalStatus.REVISION_REQUESTED.value)


async def _already_proposed(db, source_id: str) -> bool:
    """Whether this source has a proposal that must not be repeated. Plain columns only, any SQL dialect."""
    from models.approval import Approval, ApprovalType

    query = select(Approval.context).where(
        Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
        Approval.requested_by_agent == REQUESTED_BY,
        Approval.status.in_(_BLOCKING),
    )
    contexts = (await db.execute(query)).scalars().all()
    return any(c and c.get("action") == ACTION and c.get("source_id") == source_id for c in contexts)


async def propose_run_record_removal(source_id: str, source_name: str) -> str | None:
    """File the proposal for ``source_id``'s run record; returns the approval id, or ``None`` if none is needed.

    None is returned when the source has no run record, or already has a proposal that stands.
    """
    from api.codebase_analytics.run_status import describe_run_state, run_record_id
    from models.approval import ApprovalType
    from services.approval_gate_service import ApprovalGateService
    from user_management.database import get_async_session_factory

    if await describe_run_state(source_id) is None:
        return None
    record_id = run_record_id(source_id)
    async with get_async_session_factory()() as db:
        if await _already_proposed(db, source_id):
            return None
        approval = await ApprovalGateService(db).create_approval(
            title=f"Remove run record of deleted code source: {source_name}",
            approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
            description=f"The code source was deleted; its run record {record_id} (status, timestamps) remains.",
            requested_by_agent=REQUESTED_BY,
            context={"action": ACTION, "source_id": source_id, "source_name": source_name, "record_id": record_id},
        )
    return str(approval.id)


async def propose_run_record_removal_logged(source_id: str, source_name: str) -> None:
    """For the source-delete path, which must not fail on it: a failure is logged at error, the record stays."""
    try:
        if await propose_run_record_removal(source_id, source_name):
            logger.info("Raised a run record cleanup proposal for deleted source %s", source_id)
    except Exception as exc:
        logger.error("Could not raise a run record cleanup proposal for source %s (record kept): %s", source_id, exc)
