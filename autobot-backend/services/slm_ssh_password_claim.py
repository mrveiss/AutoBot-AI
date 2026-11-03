# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verify and spend an approval before the SLM deletes a stored SSH password (#20046, #17038).

The SLM's delete route is reachable with the shared internal key, which proves a service and nothing
about a human. So the SLM asks here first, and deletes only when this accepts. What is checked is what
the database keeps: ``verified_decider`` lives only on the in-memory object of the approving request, so
it cannot be read back. The durable facts are the status, the decider's name, the decision time, the
context, and the fact that the only route that approves a platform-general gate (``api.approval_gates``)
refuses anything that is not an interactive human login. Acceptance consumes the approval atomically:
the update names the unconsumed state, so two racing claims spend it once.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import literal

from autobot_shared.slm_credential_deletion import ACTION, CREDENTIAL_KIND
from models.approval import Approval, ApprovalStatus

#: ``context`` key that marks an approval as spent.
CONSUMED_KEY = "consumed_at"
#: Decider names that are not a person: the internal-key identity and the route's fallback.
_NOT_A_PERSON_PREFIXES = ("service:", "system:", "agent:")
_NOT_A_PERSON = frozenset({"", "unknown", "system"})


class ClaimRefused(Exception):
    """The approval does not authorize this deletion; the message says which check failed."""


def _refusal(approval: Approval | None, node_id: str) -> str | None:
    """Why *approval* cannot authorize deleting *node_id*'s password, or ``None`` when it can."""
    if approval is None:
        return "no such approval"
    context = approval.context or {}
    decider = str(approval.decided_by_user or "").strip()
    checks = (
        (approval.company_id is None, "not a platform-general approval"),
        (approval.status == ApprovalStatus.APPROVED.value, "approval is not approved"),
        (context.get("action") == ACTION, "approval names another action"),
        (context.get("node_id") == node_id, "approval names another node"),
        (context.get("credential_kind") == CREDENTIAL_KIND, "approval names another credential"),
        (decider not in _NOT_A_PERSON and not decider.startswith(_NOT_A_PERSON_PREFIXES), "no human decider"),
        (approval.decided_at is not None, "approval has no decision time"),
        (not context.get(CONSUMED_KEY), "approval already used"),
    )
    return next((reason for ok, reason in checks if not ok), None)


async def claim_deletion_approval(session: AsyncSession, approval_id: uuid.UUID, node_id: str) -> None:
    """Accept *approval_id* for *node_id* exactly once; raises :class:`ClaimRefused` otherwise."""
    approval = await session.get(Approval, approval_id)
    if reason := _refusal(approval, node_id):
        raise ClaimRefused(reason)
    spent = {CONSUMED_KEY: datetime.now(timezone.utc).isoformat()}
    result = await session.execute(
        update(Approval)
        .where(Approval.id == approval_id, Approval.context[CONSUMED_KEY].astext.is_(None))
        .values(context=Approval.context.concat(literal(spent, JSONB)))
    )
    if result.rowcount != 1:
        raise ClaimRefused("approval already used")
    await session.commit()
