# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wipe the knowledge base only through an approved proposal (#21048, #17038).

The KB setup script used to drop every search index and flush ten Redis databases on a bare invocation.
That is a data deletion, so it is now only *proposed*: an admin (or the operator script) raises an
ordinary approval gate, ``approval_type=destructive_action``, and nothing is deleted until a human
approves it. Approval runs :func:`execute_kb_wipe_action` through the ``services.approval_execution``
registry.

Scope is fixed in code and frozen in the approved plan: the KB's own search index and key prefixes in the
``knowledge`` Redis database (``services.kb_wipe_redis``) and the KB's own ChromaDB collections, where its
embeddings live (``services.kb_wipe_chroma``). The executor deletes exactly the plan's lists, after checking each
name against the code's scope, and never lists the server to decide what to delete. Settings, including the
embedding-model override, survive.

Known partial wipe: the pipeline loader also writes PropertyGraph nodes (``knowledge/pipeline/loaders/
redis_graph_loader.py``) that the memory graph shares. The wipe removes the loader's own ``entity:`` and
``timeline:global`` keys but NOT those shared nodes, so the KB graph is left half-wiped until ownership of
those nodes is split or KB-origin nodes are tagged (tracked in #21128).

The paper trail comes first (``knowledge/backup_audit.py``, ``services/install_cleanup_actions.py``): a durable
"intent" entry (who proposed, who approved, the frozen scope, the approval id) is committed before the first
delete, and no committed entry means nothing is deleted. The outcome entry is built step by step, so a failure
partway still records exactly what was deleted and the step reached. A self-approval follows the one four-eyes
rule (``services.approval_four_eyes``): the only admin may approve their own request, flagged; with a second
admin it is refused.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from autobot_shared.approval_four_eyes import requester_id
from autobot_shared.logging_manager import get_logger
from models.approval import Approval, ApprovalComment, ApprovalStatus, ApprovalType
from services.approval_execution import context_change_violation, register_post_approval_action, verified_decider
from services.approval_four_eyes import REFRESHED_BY_KEY, is_self_approval, proposer_ids
from services.audit.taxonomy import AuditAction
from services.audit_logger import AuditResult, audit_log
from services.kb_wipe_chroma import ChromaFactory, clear_chroma, frozen_collections, kb_collection_names, plan_chroma
from services.kb_wipe_redis import (
    KB_WIPE_DATABASES,
    ClientFactory,
    default_client,
    execute_redis,
    frozen_redis_scope,
    plan_redis,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "kb_wipe"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.kb_wipe_action"
PROPOSAL_TITLE = "Wipe the knowledge base (indexes and documents)"
#: Said to the approver in the description and in the plan: the knowledge base is one shared store.
PLATFORM_WIDE_NOTE = (
    "Platform-wide: the knowledge base is one shared store, so this removes the facts of every organisation, "
    "user and group, not one tenant's."
)
PROPOSAL_DESCRIPTION = (
    f"{PLATFORM_WIDE_NOTE} Drops the knowledge base's own search index, removes the knowledge key prefixes and "
    "empties the knowledge ChromaDB collections. Settings, boards, collections, categories and all other data "
    "are untouched."
)
_WHAT = "the knowledge wipe"
#: Where a proposal came from. Only the operator script may name a requester that is not a user id.
CHANNEL_API = "api"
CHANNEL_OPERATOR = "operator"


async def plan_kb_wipe(
    client_factory: ClientFactory = default_client, chroma_factory: ChromaFactory | None = None
) -> dict:
    """Read only: what a wipe would delete (Redis KB indexes and prefixes, Chroma KB collections), with counts."""
    stores = await asyncio.to_thread(plan_redis, client_factory)
    collections = await plan_chroma(await asyncio.to_thread(kb_collection_names), chroma_factory)
    return {
        "scope_note": PLATFORM_WIDE_NOTE,
        "databases": stores,
        "chroma_collections": collections,
        "total_keys": sum(s["keys"] for s in stores),
        "total_vectors": sum(c["vectors"] for c in collections),
    }


async def _pending_proposal(session: "AsyncSession") -> "Approval | None":
    """The pending proposal, row-locked until the caller commits.

    The lock serialises a refresh against a decision: the approval's conditional ``pending -> approved`` update
    waits for the refresh to commit, and a refresh that starts after the approval committed no longer matches the
    row, so it proposes anew instead of rewriting the plan an approver already holds.
    """
    query = (
        select(Approval)
        .where(Approval.status == ApprovalStatus.PENDING.value, Approval.context["action"].astext == ACTION)
        .with_for_update()
    )
    return (await session.execute(query)).scalars().first()


def _proposal_context(requested_by: str, channel: str, plan: dict) -> dict:
    return {
        "action": ACTION,
        "requested_by": requested_by,
        "channel": channel,
        "databases": list(KB_WIPE_DATABASES),
        "plan": plan,
    }


def _count_changes(old: object, new: dict) -> dict:
    """Old and new scope totals, as ``[before, after]`` pairs; no document content."""
    old = old if isinstance(old, dict) else {}
    return {k: [old.get(k), new.get(k)] for k in ("total_keys", "total_vectors")}


def _reviewed_fields(context: dict) -> dict:
    """The context minus the two keys a refresh may change; the rest is what the approver reviewed (#17349)."""
    return {k: v for k, v in context.items() if k not in ("plan", REFRESHED_BY_KEY)}


async def _refresh_pending(session: "AsyncSession", pending: "Approval", requested_by: str, plan: dict) -> None:
    """Re-propose a pending wipe: the plan is replaced, the refresh is recorded durably, the requester stays.

    The same freeze as a resubmit applies (``context_change_violation``): only ``plan`` and ``refreshed_by`` move.
    The refresher joins ``refreshed_by``, so four eyes treats them as a proposer. The durable audit entry comes
    first; without it the plan is not changed.
    """
    old = pending.context or {}
    new = {**old, "plan": plan, REFRESHED_BY_KEY: [*(old.get(REFRESHED_BY_KEY) or []), requested_by]}
    if (changed := context_change_violation(_reviewed_fields(old), _reviewed_fields(new))) is not None:
        raise ValueError(f"{_WHAT} proposal: {changed} cannot change on a refresh")
    counts = _count_changes(old.get("plan"), plan)
    details = {"approval_id": str(pending.id), "phase": "plan_refresh", "refreshed_by": requested_by, "counts": counts}
    if not await audit_log(
        AuditAction.KNOWLEDGE_WIPE_REFRESH.value,
        user_id=requested_by,
        resource="knowledge_base",
        durable=True,
        details=details,
    ):
        raise RuntimeError(f"the audit entry for refreshing approval {pending.id} could not be written; plan unchanged")
    pending.context = new
    keys, vectors = counts["total_keys"], counts["total_vectors"]
    body = f"Plan refreshed by {requested_by}: keys {keys}, vectors {vectors} (before, after)."
    session.add(ApprovalComment(approval_id=pending.id, author="system", author_type="system", body=body))
    await session.commit()


async def propose_kb_wipe(
    session: "AsyncSession", requested_by: str, plan: dict, *, channel: str = CHANNEL_API
) -> "Approval":
    """Raise (or reuse, with its counts refreshed) the one pending #17038 proposal. Deletes nothing.

    An advisory lock held until the transaction commits serialises concurrent proposers, so two
    requests cannot both see "no pending proposal" and both insert one.
    """
    from services.approval_gate_service import ApprovalGateService

    if channel == CHANNEL_API and requester_id(requested_by) is None:
        # Refused before any row exists: a proposal the review hook would always refuse could never be decided
        # and would block every later proposal behind it.
        raise ValueError(f"{_WHAT} can be proposed on the API channel only by a user id")
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": ACTION})
    if (pending := await _pending_proposal(session)) is not None:
        await _refresh_pending(session, pending, requested_by, plan)
        return pending
    return await ApprovalGateService(session).create_approval(
        title=PROPOSAL_TITLE,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=PROPOSAL_DESCRIPTION,
        requested_by_agent=f"kb-wipe:{requested_by}",
        context=_proposal_context(requested_by, channel, plan),
    )


async def _review_kb_wipe(approval: "Approval", session: "AsyncSession") -> bool:
    """Four eyes, before the decision commits: True for the only admin approving their own request.

    A requester that names no person passes unflagged only on the operator-script channel, which cannot
    authenticate, and only while no admin has refreshed its plan (a refresher is a proposer). On the API channel
    it fails closed: the decision is refused, never waved through.
    """
    if requester_id(approval.requested_by_agent) is None:
        if (approval.context or {}).get("channel") != CHANNEL_OPERATOR:
            raise ValueError(f"{_WHAT} was proposed by a requester that names no user; it cannot be approved")
        if not proposer_ids(approval):  # nobody refreshed it either: there is no person to compare the decider to
            return False
    return await is_self_approval(approval, session, what=_WHAT)


def _details(approval: "Approval", self_approval: bool, **extra: object) -> dict:
    """Who proposed, who approved and under which approval id; no document content."""
    return {
        "approval_id": str(approval.id),
        "proposed_by": approval.requested_by_agent,
        "approved_by": approval.decided_by_user,
        "approver_id": str(verified_decider(approval)),
        "approved_at": approval.decided_at.isoformat() if approval.decided_at else None,
        "self_approval": self_approval,
        **extra,
    }


def _outcome_details(
    approval: "Approval", self_approval: bool, record: dict, error: str | None = None, **extra: object
) -> dict:
    steps = len(record["redis"]) + len(record["chroma"])
    return _details(
        approval,
        self_approval,
        step=record["step"],
        steps_started=steps,
        collections=record["collections"],
        redis=record["redis"],
        chroma=record["chroma"],
        error=error,
        **extra,
    )


async def _audit(approval: "Approval", result: AuditResult, details: dict) -> bool:
    """Whether the durable entry was committed."""
    return await audit_log(
        AuditAction.KNOWLEDGE_WIPE.value,
        result=result,
        user_id=approval.decided_by_user,
        resource="knowledge_base",
        durable=True,
        details=details,
    )


def _require_approved(approval: "Approval") -> None:
    if (approval.context or {}).get("action") != ACTION or approval.status != ApprovalStatus.APPROVED.value:
        raise ValueError(f"approval {approval.id} is not an approved {ACTION} proposal; the wipe is refused")


async def _frozen_scope(approval: "Approval") -> dict:
    """Exactly what the approved plan says to delete, checked against the code's scope, before anything is deleted."""
    plan = (approval.context or {}).get("plan")
    if not isinstance(plan, dict):
        raise ValueError(f"approval {approval.id} carries no plan; the wipe is refused")
    allowed = await asyncio.to_thread(kb_collection_names)  # read now: the wipe changes what this reads
    try:
        return {
            "redis": frozen_redis_scope(plan["databases"]),
            "collections": frozen_collections(plan["chroma_collections"], allowed),
        }
    except (KeyError, TypeError) as exc:
        raise ValueError(f"approval {approval.id} carries a malformed plan; the wipe is refused") from exc


async def _record_intent(approval: "Approval", scope: dict, self_approval: bool) -> None:
    """The paper trail comes first: no committed entry means nothing is deleted (#17038)."""
    details = _details(approval, self_approval, phase="intent", scope=scope)
    if not await _audit(approval, "attempted", details):
        raise RuntimeError(f"the audit entry for approval {approval.id} could not be written; nothing was deleted")


async def _audit_failure(approval: "Approval", record: dict, self_approval: bool, exc: Exception) -> None:
    """Record the failed outcome. Never raises, so the wipe's own error stays the one that propagates (#17038)."""
    details = _outcome_details(approval, self_approval, record, error=type(exc).__name__, phase="failure")
    outcome = "returned False"
    try:
        if await _audit(approval, "failed", details):
            return
    except Exception as audit_exc:  # noqa: BLE001 -- logged below; it must not replace the original error
        outcome = type(audit_exc).__name__
    logger.error("knowledge wipe: the failure audit entry for approval %s was not written (%s)", approval.id, outcome)


async def _wipe(approval: "Approval", scope: dict, self_approval: bool) -> dict:
    """Redis, then Chroma, each exactly as frozen; a failure audits what was already deleted, then re-raises."""
    record: dict = {"step": "redis", "collections": scope["collections"], "redis": [], "chroma": []}
    try:
        await asyncio.to_thread(execute_redis, record["redis"], scope["redis"])
        record["step"] = "chroma"
        await clear_chroma(scope["collections"], record["chroma"])
    except Exception as exc:
        await _audit_failure(approval, record, self_approval, exc)
        raise
    return record


def _summary(record: dict) -> str:
    parts = [f"{s['kind']} {s['name']} ({s['count']})" for s in record["redis"]]
    parts += [f"chroma {c['name']} ({c['vectors']} vectors)" for c in record["chroma"]]
    return "Knowledge wipe done: " + ", ".join(parts)


async def execute_kb_wipe_action(approval: "Approval", session: "AsyncSession") -> None:
    """Wipe the KB for an approved gate: the intent entry first, then the frozen scope, then the outcome entry."""
    _require_approved(approval)
    if verified_decider(approval) is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the wipe is refused")
    self_approval = await _review_kb_wipe(approval, session)
    scope = await _frozen_scope(approval)
    await _record_intent(approval, scope, self_approval)
    record = await _wipe(approval, scope, self_approval)
    if not await _audit(approval, "success", _outcome_details(approval, self_approval, record, phase="completion")):
        raise RuntimeError(f"the wipe for approval {approval.id} ran but its audit record could not be written")
    body = _summary(record) + (" (self-approved by the only admin)." if self_approval else ".")
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


def register_kb_wipe_action() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler."""
    register_post_approval_action(
        ACTION,
        execute_kb_wipe_action,
        proposed_by=PROPOSED_BY,
        server_only=True,
        admin_only=True,
        review=_review_kb_wipe,
    )


__all__ = [
    "ACTION",
    "CHANNEL_API",
    "CHANNEL_OPERATOR",
    "KB_WIPE_DATABASES",
    "PROPOSED_BY",
    "execute_kb_wipe_action",
    "plan_kb_wipe",
    "propose_kb_wipe",
    "register_kb_wipe_action",
]
