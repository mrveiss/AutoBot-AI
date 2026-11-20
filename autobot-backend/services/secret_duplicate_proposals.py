# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Proposes how to resolve duplicated secrets; a human decides (#17850, #17038).

Every ``(owner_vault, name)`` group with more than one row is verified copy by copy
(``services/secret_duplicates.py``). Exactly one copy verifies: the proposal names it as the survivor and the
others as the removals. Zero or several verify, or the type has no verifier: the proposal carries NO survivor
and is flagged for a person's choice. Either way it only asks: it deletes nothing, cannot approve itself, and
never expires into approval. It names ``"secret_duplicate_cleanup"``, which
``services/secret_duplicate_cleanup_action.py`` runs once a human approves.

The proposal holds ids and a reason code only -- no name, no value. A group with a pending, rejected or
revision-requested proposal is not proposed again: a denial is a person's decision and stays one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.constant_time import secure_compare
from models.approval import Approval, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.secret_duplicate_cleanup_action import ACTION, register_secret_duplicate_cleanup_action
from services.secret_duplicates import GroupVerification, Verdict, find_duplicate_groups, verify_group

logger = get_logger(__name__)

REQUESTED_BY = "secret-duplicate-resolution"

# Registered at import: the handler must be in place before any approve() can reach a proposal raised here.
register_secret_duplicate_cleanup_action()

#: Proposal states that keep a group from being proposed again. A denial is a person's decision, so it stands --
#: until an admin explicitly re-raises the group, which only a still-PENDING proposal then blocks.
_BLOCKING = (ApprovalStatus.PENDING.value, ApprovalStatus.REJECTED.value, ApprovalStatus.REVISION_REQUESTED.value)
_BLOCKING_WHEN_RE_RAISED = (ApprovalStatus.PENDING.value,)

#: Most groups one request verifies and proposes (each copy is a network probe); the rest are reported (#17850).
MAX_GROUPS_PER_REQUEST = env_int_clamped("AUTOBOT_SECRET_DUPLICATE_MAX_GROUPS_PER_REQUEST", 5, 1, 100)

REASON_ONE = "one_verified"
REASON_NONE = "none_verified"
REASON_SEVERAL = "several_verified"
REASON_NO_VERIFIER = "no_verifier"


@dataclass(frozen=True)
class ProposalBatch:
    """The results of one request and how many duplicated groups it left for another call."""

    results: list["ProposalResult"]
    remaining: int


@dataclass(frozen=True)
class ProposalResult:
    """What one group produced: the approval raised, or why none was."""

    approval_id: str | None
    reason: str
    copies: int
    skipped: bool = False


def _reason(result: GroupVerification) -> str:
    if Verdict.NO_VERIFIER in result.verdicts.values():
        return REASON_NO_VERIFIER
    return {0: REASON_NONE, 1: REASON_ONE}.get(len(result.verified_ids), REASON_SEVERAL)


def group_digest(secret_ids) -> str:
    """Identity of a group for de-duplicating proposals: a digest of its sorted ids."""
    return hashlib.sha256(",".join(sorted(str(i) for i in secret_ids)).encode("utf-8")).hexdigest()[:32]


def proposal_context(result: GroupVerification) -> dict:
    """The reviewed payload: ids and a reason code only. ``survivor_id`` is null when a person must choose."""
    ids = sorted(str(i) for i in result.group.secret_ids)
    survivor = result.survivor_id
    return {
        "action": ACTION,
        "group_digest": group_digest(ids),
        "secret_ids": ids,
        "verified_ids": [str(i) for i in result.verified_ids],
        "versions": {str(i): v for i, v in zip(result.group.secret_ids, result.group.versions, strict=False)},
        "survivor_id": str(survivor) if survivor else None,
        "removal_ids": [i for i in ids if survivor and i != str(survivor)],
        "reason": _reason(result),
    }


async def _already_proposed(db: AsyncSession, digest: str, re_raise: bool = False) -> bool:
    """Whether this group has a proposal that must not be repeated. Plain columns only, any SQL dialect."""
    query = select(Approval.context).where(
        Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
        Approval.requested_by_agent.like(f"{REQUESTED_BY}%"),
        Approval.status.in_(_BLOCKING_WHEN_RE_RAISED if re_raise else _BLOCKING),
    )
    contexts = (await db.execute(query)).scalars().all()
    return any(c and c.get("action") == ACTION and secure_compare(c.get("group_digest"), digest) for c in contexts)


async def pending_proposals(db: AsyncSession) -> dict[str, str]:
    """``group_digest -> approval id`` of every PENDING proposal, so the admin view can link a group to its review."""
    query = select(Approval.id, Approval.context).where(
        Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
        Approval.requested_by_agent.like(f"{REQUESTED_BY}%"),
        Approval.status == ApprovalStatus.PENDING.value,
    )
    return {c["group_digest"]: str(i) for i, c in (await db.execute(query)).all() if c and c.get("action") == ACTION}


def _text(context: dict) -> tuple[str, str]:
    copies = len(context["secret_ids"])
    if context["survivor_id"]:
        return (
            f"Remove {len(context['removal_ids'])} unverified duplicate secret copies",
            f"{copies} secrets share one name and vault. Exactly one verified against its target and is kept; "
            "approving removes the others. Nothing is removed until a person approves.",
        )
    return (
        f"Choose which of {copies} duplicate secret copies to keep",
        f"{copies} secrets share one name and vault; no recommendation ({context['reason']}). Approving removes "
        "nothing: keep the copy you choose and delete the others through the secrets delete route.",
    )


async def propose_group(
    db: AsyncSession, result: GroupVerification, requester: str, re_raise: bool = False
) -> ProposalResult:
    """File the proposal for one verified group; skipped when one already stands for it (see ``re_raise``)."""
    context = proposal_context(result)
    copies = len(context["secret_ids"])
    if await _already_proposed(db, context["group_digest"], re_raise):
        return ProposalResult(None, context["reason"], copies, skipped=True)
    title, description = _text(context)
    approval = await ApprovalGateService(db).create_approval(
        title=title,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=description,
        requested_by_agent=f"{REQUESTED_BY}:{requester}",
        context=context,
    )
    return ProposalResult(str(approval.id), context["reason"], copies)


async def propose_duplicate_resolutions(
    db: AsyncSession, requester: str, *, re_raise: bool = False, limit: int | None = None
) -> ProposalBatch:
    """Detect, verify and propose for duplicated ``(owner_vault, name)`` groups, probing at most *limit* per call.

    ``re_raise`` lets an admin raise a group again after a rejected or revision-requested proposal. A group with a
    standing proposal is skipped before any probe and does not count against the cap; groups past the cap are
    counted in ``remaining`` for the next call, so repeated calls always make progress.
    """
    cap = MAX_GROUPS_PER_REQUEST if limit is None else limit
    results: list[ProposalResult] = []
    probed = remaining = 0
    for group in await find_duplicate_groups(db):
        if await _already_proposed(db, group_digest(group.secret_ids), re_raise):
            results.append(ProposalResult(None, "already_proposed", len(group.secret_ids), skipped=True))
        elif probed >= cap:
            remaining += 1
        else:
            probed += 1
            results.append(await propose_group(db, await verify_group(db, group), requester, re_raise))
    logger.info("Secret duplicate resolution: %d proposed, %d left for another call", probed, remaining)
    return ProposalBatch(results, remaining)
