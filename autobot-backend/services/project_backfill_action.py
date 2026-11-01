# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an approved request to give a company's project-less work items a project (#18978, #17038).

Nothing is written until a PERSON approves. The proposer (``services.project_backfill_proposal``) files an
approval whose context names this action and the company; on approval this handler recounts the company's
rows (it never trusts the preview a person looked at) and performs the backfill in
``llc.services.project_backfill``. It REFUSES when the decider is not an owner or admin of that company, or
when the requester decided their own request while the company has two or more owners/admins (four eyes).
A second run finds nothing to do and writes an audit row saying so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autobot_shared.logging_manager import get_logger
from llc.services.authz import require_company_admin
from llc.services.project_backfill import apply_project_backfill
from models.approval import ApprovalComment, ApprovalStatus
from services.ai_line_change_action import require_four_eyes
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

ACTION = "llc.project_backfill"
PROPOSED_BY = "services.project_backfill_proposal"


async def execute_project_backfill(approval: "Approval", session: "AsyncSession") -> None:
    """Apply the approved backfill to the approval's company. Raises (recorded by the dispatcher) when it must not."""
    if approval.status != ApprovalStatus.APPROVED.value or approval.company_id is None:
        raise ValueError("not an approved, company-scoped project backfill")
    decider = verified_decider(approval)  # the authenticated person's id, never parsed from a username
    await require_company_admin(session, approval.company_id, decider)
    self_approval = await require_four_eyes(approval, session, decider)
    counts = await apply_project_backfill(session, approval.company_id)
    note = " (self-approved)" if self_approval else ""
    body = (
        f"Project backfill: {counts['missing']} item(s) without a project; {counts['from_ancestor']} took an "
        f"ancestor's project, {counts['to_default']} went to the default project{note}; "
        f"{counts['foreign_ancestor_project_skipped']} had an ancestor in another company's project (not used)."
    )
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await audit_log(
        "llc.project_backfill",
        result="success",
        user_id=approval.decided_by_user,
        resource=str(approval.company_id),
        details={"approval_id": str(approval.id), "self_approval": self_approval, **counts},
    )


def register_project_backfill_action() -> None:
    """Register the handler; called when the approval routers load, before any approve()."""
    register_post_approval_action(ACTION, execute_project_backfill, proposed_by=PROPOSED_BY, server_only=True)
