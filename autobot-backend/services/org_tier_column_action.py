# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Drop ``organizations.subscription_tier`` only after a human approves it (#19997, #17038).

AutoBot has no paid tiers, and the code stopped using the column in #19984. A migration would drop
stored data on every host's next update with nobody asked, so this is a proposal in the review queue
instead. Until it is approved the column just stays: it is nullable and nothing reads it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action
from services.approval_four_eyes import is_self_approval
from services.audit.outcome import FAILED, SUCCESS, record_control_attempt, record_control_outcome

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval
    from services.audit.taxonomy import AuditEvent

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "org_subscription_tier_drop"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.admin_org_tier_column"

_COLUMN_PRESENT = text(
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = 'organizations' AND column_name = 'subscription_tier'"
)
_DROP = text("ALTER TABLE organizations DROP COLUMN IF EXISTS subscription_tier")


async def column_present(session: "AsyncSession") -> bool:
    """Whether this database still holds the column; a fresh install never had it."""
    return (await session.execute(_COLUMN_PRESENT)).first() is not None


async def _record_drop_attempt(approval: "Approval", **details: object) -> "AuditEvent":
    """The ``attempted`` row, through the shared helper; with none committed the schema is not touched (#22130)."""
    attempt = await record_control_attempt(
        "org.subscription_tier.drop",
        user_id=approval.decided_by_user,
        resource="organizations.subscription_tier",
        details={"approval_id": str(approval.id), **details},
    )
    if attempt is None:
        raise RuntimeError("the audit entry could not be written, so the column was not dropped")
    return attempt


async def _review_drop(approval: "Approval", session: "AsyncSession") -> bool:
    """The four-eyes check on the drop, run before the decision commits and again before the drop."""
    return await is_self_approval(approval, session, what="the drop")


async def execute_tier_column_drop(approval: "Approval", session: "AsyncSession") -> None:
    """Drop the column an approved gate named; the audit entry is written before the schema changes.

    The decider check re-runs here, after the commit, so an admin leaving in that window can still leave the row
    approved and unapplied with a comment; that is accepted.
    """
    self_approval = await _review_drop(approval, session)
    was_present = await column_present(session)
    flags = {"self_approval": self_approval, "was_present": was_present}
    attempt = await _record_drop_attempt(approval, stage="started", **flags)
    try:
        await session.execute(_DROP)
    except BaseException as exc:  # a cancelled drop is an outcome too; the error that raised stays the one raised
        await record_control_outcome(attempt, FAILED, type(exc).__name__, {"stage": "failed"})
        raise
    body = "Dropped organizations.subscription_tier" if was_present else "organizations.subscription_tier was gone"
    body += " (self-approved by the only admin)." if self_approval else "."
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await record_control_outcome(attempt, SUCCESS, details={"stage": "done"})


def register_tier_column_action() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(
        ACTION, execute_tier_column_drop, proposed_by=PROPOSED_BY, server_only=True, review=_review_drop
    )


__all__ = ["ACTION", "PROPOSED_BY", "column_present", "execute_tier_column_drop", "register_tier_column_action"]
