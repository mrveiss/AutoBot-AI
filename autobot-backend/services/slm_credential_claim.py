# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verify and spend an approval before a stored credential is changed (#20046, #20750, #17038).

The side that applies the change (the SLM deleting a stored SSH password, the updater re-aligning the
backend's internal key) authenticates with the shared internal key, which proves a service and nothing
about a human. So it asks here first, and changes the credential only when this accepts. What is checked is what
the database keeps: ``verified_decider`` lives only on the in-memory object of the approving request, so
it cannot be read back. The durable facts are the status, the decider's name, the decision time, the
context, and the fact that the only route that approves a platform-general gate (``api.approval_gates``)
refuses anything that is not an interactive human login. Acceptance consumes the approval atomically:
the update names the unconsumed state, so two racing claims spend it once.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import literal

from autobot_shared.slm_credential_actions import CredentialAction
from models.approval import Approval, ApprovalStatus

#: ``context`` key that marks an approval as spent.
CONSUMED_KEY = "consumed_at"
#: Decider names that are not a person: the internal-key identity and the route's fallback.
_NOT_A_PERSON_PREFIXES = ("service:", "system:", "agent:")
_NOT_A_PERSON = frozenset({"", "unknown", "system"})


class ClaimRefused(Exception):
    """The approval does not authorize this change; the message says which check failed."""


class ClaimNotRecorded(Exception):
    """The durable record of the claim could not be written, so the approval was NOT spent (#17038)."""


def _refusal(approval: Approval | None, action: CredentialAction, node_id: str) -> str | None:
    """Why *approval* cannot authorize *action* on *node_id*, or ``None`` when it can."""
    if approval is None:
        return "no such approval"
    context = approval.context or {}
    decider = str(approval.decided_by_user or "").strip()
    checks = (
        (approval.company_id is None, "not a platform-general approval"),
        (approval.status == ApprovalStatus.APPROVED.value, "approval is not approved"),
        (context.get("action") == action.name, "approval names another action"),
        (context.get("node_id") == node_id, "approval names another node"),
        (context.get("credential_kind") == action.credential_kind, "approval names another credential"),
        (decider not in _NOT_A_PERSON and not decider.startswith(_NOT_A_PERSON_PREFIXES), "no human decider"),
        (approval.decided_at is not None, "approval has no decision time"),
        (not context.get(CONSUMED_KEY), "approval already used"),
    )
    return next((reason for ok, reason in checks if not ok), None)


async def claim_approval(
    session: AsyncSession,
    approval_id: uuid.UUID,
    action: CredentialAction,
    node_id: str,
    record_first: Callable[[Approval], Awaitable[bool]] | None = None,
) -> Approval:
    """Accept *approval_id* for *action* on *node_id* exactly once; raises :class:`ClaimRefused` otherwise.

    *record_first* writes the durable audit row after the checks pass and BEFORE the approval is spent;
    if it reports failure nothing is spent and :class:`ClaimNotRecorded` is raised, so a change is never
    authorized without its paper trail (#17038).
    """
    approval = await session.get(Approval, approval_id)
    if reason := _refusal(approval, action, node_id):
        raise ClaimRefused(reason)
    if record_first is not None and not await record_first(approval):
        raise ClaimNotRecorded("the claim could not be recorded")
    spent = {CONSUMED_KEY: datetime.now(timezone.utc).isoformat()}
    result = await session.execute(
        update(Approval)
        .where(Approval.id == approval_id, Approval.context[CONSUMED_KEY].astext.is_(None))
        .values(context=Approval.context.concat(literal(spent, JSONB)))
    )
    if result.rowcount != 1:
        raise ClaimRefused("approval already used")
    await session.commit()
    return approval


#: ``context`` key holding the one terminal outcome an applying side reported (#20750).
OUTCOME_KEY = "outcome"
#: The most of a reported detail that is kept: it reaches an audit row and an approval comment.
_DETAIL_MAX = 300


class OutcomeRefused(Exception):
    """No claimed approval for this action and node, or its outcome is already recorded."""


def clean_detail(detail: str) -> str:
    """A reported detail as plain one-line text, capped: no control characters, newlines or markup runs."""
    printable = "".join(ch if ch.isprintable() else " " for ch in detail)
    return " ".join(printable.split())[:_DETAIL_MAX]


async def record_outcome(
    session: AsyncSession, approval_id: uuid.UUID, action: CredentialAction, node_id: str, result: str
) -> Approval:
    """Record the ONE terminal outcome of a claimed approval; a second report is refused, never overwritten."""
    approval = await session.get(Approval, approval_id)
    context = (approval.context or {}) if approval else {}
    if (
        approval is None
        or context.get("action") != action.name
        or context.get("node_id") != node_id
        or not context.get(CONSUMED_KEY)
    ):
        raise OutcomeRefused("no claimed approval for this action and node")
    stamped = {OUTCOME_KEY: result}
    written = await session.execute(
        update(Approval)
        .where(
            Approval.id == approval_id,
            Approval.context[CONSUMED_KEY].astext.is_not(None),
            Approval.context[OUTCOME_KEY].astext.is_(None),
        )
        .values(context=Approval.context.concat(literal(stamped, JSONB)))
    )
    if written.rowcount != 1:
        raise OutcomeRefused("the outcome is already recorded")
    return approval
