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
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

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


async def execute_tier_column_drop(approval: "Approval", session: "AsyncSession") -> None:
    """Drop the column an approved gate named, and record what happened."""
    was_present = await column_present(session)
    await session.execute(_DROP)
    body = "Dropped organizations.subscription_tier." if was_present else "organizations.subscription_tier was gone."
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await audit_log(
        "organizations.subscription_tier.drop",
        result="success",
        user_id=approval.decided_by_user,
        resource="organizations.subscription_tier",
        details={"approval_id": str(approval.id), "was_present": was_present},
    )


def register_tier_column_action() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(ACTION, execute_tier_column_drop, proposed_by=PROPOSED_BY)


__all__ = ["ACTION", "PROPOSED_BY", "column_present", "execute_tier_column_drop", "register_tier_column_action"]
