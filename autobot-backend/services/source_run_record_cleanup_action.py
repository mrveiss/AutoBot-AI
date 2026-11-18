# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an APPROVED proposal to remove a deleted code source's run record (#21417, #17038).

Deleting a code source leaves its run record (status, timestamps, counts) in the code collection:
the record deliberately carries no ``source_id`` key, so the source's document purge never matches it.
Removing it is deletion of stored data, so ``api/codebase_analytics/source_service.py`` only PROPOSES it
(``services/source_run_record_cleanup_proposals.py``). The proposal is an ordinary approval gate::

    {"action": "source_run_record_cleanup", "source_id": "...", "source_name": "...", "record_id": "..."}

Approving it runs :func:`execute_source_run_record_cleanup` through ``services.approval_execution``.
The record to remove is computed again from ``source_id`` at execution -- ``record_id`` is only what the
reviewer reads -- so an approval removes exactly that source's record and nothing else. The outcome lands
as a comment on the approval and as a durable audit entry (#17038 rule 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "source_run_record_cleanup"

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.source_run_record_cleanup_proposals"


async def execute_source_run_record_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove the run record an approved gate named, and record what happened."""
    from api.codebase_analytics.run_status import delete_run_record, run_record_id

    source_id = (approval.context or {}).get("source_id")
    if not source_id:
        # #17141: raise, so the dispatcher records the failure durably.
        raise ValueError(f"approval {approval.id} is missing source_id in its action context")

    record_id = run_record_id(source_id)
    removed = await delete_run_record(source_id)
    outcome = "removed" if removed else "found nothing to remove for"
    body = f"Source run record cleanup {outcome} {record_id}"
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await audit_log(
        AuditAction.CODE_SOURCE_RUN_RECORD_CLEANUP.value,
        result="success" if removed else "failed",
        user_id=approval.decided_by_user,
        resource=f"run_record:{record_id}",
        details={"approval_id": str(approval.id), "source_id": source_id},
    )


def register_source_run_record_cleanup_action() -> None:
    """Idempotent. Server-only: the source is the proposer's to name, never a caller's."""
    register_post_approval_action(ACTION, execute_source_run_record_cleanup, proposed_by=PROPOSED_BY, server_only=True)


__all__ = ["ACTION", "PROPOSED_BY", "execute_source_run_record_cleanup", "register_source_run_record_cleanup_action"]
