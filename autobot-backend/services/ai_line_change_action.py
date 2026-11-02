# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an approved request to change one AI line (#18430, #17038).

Agents never change a line. The proposer (``services.ai_line_change_proposal``) files an approval
whose context names this action; nothing is written until a PERSON approves it, and on approval
this handler is the only caller of ``llc.services.ai_lines.record_approved_line``. It REFUSES, with a
durable comment, when:

* the approval carries no scope, or a malformed key or line;
* the approval was not decided by a person who is an owner or admin of THAT company -- the
  generic approval endpoint does not check company membership, so this handler must;
* a PERSONAL line (a user with no company) is decided by anyone but the person it belongs to;
* the requester decided their own request while the company has two or more owners/admins (four eyes,
  owner decision #18430). A company with a single owner/admin may self-approve; that is flagged in the audit.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from autobot_shared.ai_lines import SCOPE_COMPANY, SCOPE_USER, LineScope, parse_line
from autobot_shared.logging_manager import get_logger
from llc.services.ai_lines import normalise_key, record_approved_line
from llc.services.authz import require_company_admin, require_four_eyes
from models.approval import ApprovalComment, ApprovalStatus
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

ACTION = "ai_line.set_line"
PROPOSED_BY = "services.ai_line_change_proposal"


async def _trail(
    approval: "Approval", session: "AsyncSession", body: str, result: str, self_approval: bool = False
) -> None:
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await audit_log(
        "ai_line.change",
        result=result,
        user_id=approval.decided_by_user,
        resource=str((approval.context or {}).get("action_key")),
        details={
            "approval_id": str(approval.id),
            "company_id": str(approval.company_id),
            "self_approval": self_approval,
        },
    )


async def _scope_and_review(
    approval: "Approval", session: "AsyncSession", decider: uuid.UUID | None
) -> tuple[LineScope, bool]:
    """The scope this change is for and whether it is a self-approval; raises when the decider may not decide it.

    Company: an owner or admin of that company, and four eyes when it has two or more. Personal: only the user
    the lines belong to (there is no second admin in a personal scope), always flagged as a self-approval.
    """
    ctx = approval.context or {}
    if ctx.get("scope_kind") == SCOPE_USER:
        owner = uuid.UUID(str(ctx.get("scope_id")))
        if decider is None or decider != owner:
            raise ValueError("a personal line can be changed only by the person it belongs to")
        return LineScope(SCOPE_USER, owner), True
    if approval.company_id is None:
        raise ValueError("not a company-scoped or personal request")
    await require_company_admin(session, approval.company_id, decider)
    return LineScope(SCOPE_COMPANY, approval.company_id), await require_four_eyes(
        approval, session, decider, what="a line change"
    )


async def execute_line_change(approval: "Approval", session: "AsyncSession") -> None:
    """Apply the approved line. Raises (recorded by the dispatcher) when it must not."""
    ctx = approval.context or {}
    line = parse_line(ctx.get("line"))
    if approval.status != ApprovalStatus.APPROVED.value or line is None:
        raise ValueError("not an approved request naming one of the three lines")
    key = normalise_key(str(ctx.get("action_key", "")))
    decider = verified_decider(approval)  # the authenticated person's id, never parsed from a username
    scope, self_approval = await _scope_and_review(approval, session, decider)
    await record_approved_line(
        session,
        company_id=scope.id,
        kind=scope.kind,
        key=key,
        line=line,
        approval_id=approval.id,
        decided_by=str(approval.decided_by_user),
    )
    note = " (self-approved)" if self_approval else ""
    await _trail(approval, session, f"AI line for '{key}' is now {line.value}{note}.", "success", self_approval)


def register_ai_line_change_action() -> None:
    """Register the handler; called when the approval-gates router loads, before any approve()."""
    register_post_approval_action(ACTION, execute_line_change, proposed_by=PROPOSED_BY, server_only=True)
