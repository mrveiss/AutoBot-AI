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

Scope is fixed in code, never read from the approval: the KB search indexes and key prefixes in the
``knowledge`` Redis database (``services.kb_wipe_redis``) and the KB's own ChromaDB collections, where its
embeddings live (``services.kb_wipe_chroma``). Settings, including the embedding-model override, survive.

The audit record is built step by step, so a failure partway still records exactly what was deleted. A
self-approval follows the one four-eyes rule (``services.approval_four_eyes``): the only admin may approve
their own request, flagged; with a second admin it is refused.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from autobot_shared.approval_four_eyes import requester_id
from autobot_shared.logging_manager import get_logger
from models.approval import Approval, ApprovalComment, ApprovalStatus, ApprovalType
from services.approval_execution import register_post_approval_action, verified_decider
from services.approval_four_eyes import is_self_approval
from services.audit_logger import AuditResult, audit_log
from services.kb_wipe_chroma import ChromaFactory, clear_chroma, kb_collection_names, plan_chroma
from services.kb_wipe_redis import KB_WIPE_DATABASES, ClientFactory, default_client, execute_redis, plan_redis

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "kb_wipe"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.kb_wipe_action"
PROPOSAL_TITLE = "Wipe the knowledge base (indexes and documents)"
_WHAT = "the knowledge wipe"


async def plan_kb_wipe(
    client_factory: ClientFactory = default_client, chroma_factory: ChromaFactory | None = None
) -> dict:
    """Read only: what a wipe would delete (Redis KB indexes and prefixes, Chroma KB collections), with counts."""
    stores = await asyncio.to_thread(plan_redis, client_factory)
    collections = await plan_chroma(await asyncio.to_thread(kb_collection_names), chroma_factory)
    return {
        "databases": stores,
        "chroma_collections": collections,
        "total_keys": sum(s["keys"] for s in stores),
        "total_vectors": sum(c["vectors"] for c in collections),
    }


async def propose_kb_wipe(session: "AsyncSession", requested_by: str, plan: dict) -> "Approval":
    """Raise (or reuse, with its counts refreshed) the one pending #17038 proposal. Deletes nothing.

    An advisory lock held until the transaction commits serialises concurrent proposers, so two
    requests cannot both see "no pending proposal" and both insert one.
    """
    from services.approval_gate_service import ApprovalGateService

    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": ACTION})
    query = select(Approval).where(
        Approval.status == ApprovalStatus.PENDING.value, Approval.context["action"].astext == ACTION
    )
    context = {"action": ACTION, "requested_by": requested_by, "databases": list(KB_WIPE_DATABASES), "plan": plan}
    if (pending := (await session.execute(query)).scalars().first()) is not None:
        pending.context = {**(pending.context or {}), "plan": plan}
        await session.commit()
        return pending
    return await ApprovalGateService(session).create_approval(
        title=PROPOSAL_TITLE,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=(
            "Drops the knowledge search indexes, removes the knowledge key prefixes and empties the knowledge "
            "ChromaDB collections. Settings and all other data are untouched."
        ),
        requested_by_agent=f"kb-wipe:{requested_by}",
        context=context,
    )


async def _review_kb_wipe(approval: "Approval", session: "AsyncSession") -> bool:
    """Four eyes, before the decision commits: True for the only admin approving their own request.

    A requester that names no person (the operator script) is not the decider, so it passes unflagged.
    """
    if requester_id(approval.requested_by_agent) is None:
        return False
    return await is_self_approval(approval, session, what=_WHAT)


async def _audit(
    approval: "Approval", result: AuditResult, record: dict, self_approval: bool, error: str | None = None
) -> bool:
    return await audit_log(
        "knowledge.wipe",
        result=result,
        user_id=approval.decided_by_user,
        resource="knowledge_base",
        durable=True,
        details={
            "approval_id": str(approval.id),
            "approved_by": approval.decided_by_user,
            "approver_id": str(verified_decider(approval)),
            "approved_at": approval.decided_at.isoformat() if approval.decided_at else None,
            "self_approval": self_approval,
            "collections": record["collections"],
            "redis": record["redis"],
            "chroma": record["chroma"],
            "error": error,
        },
    )


async def _wipe(approval: "Approval", self_approval: bool) -> dict:
    """Resolve the collections first, then Redis, then Chroma; a failure audits what was already deleted."""
    record: dict = {"collections": [], "redis": [], "chroma": []}
    try:
        record["collections"] = await asyncio.to_thread(kb_collection_names)  # before anything is deleted
        await asyncio.to_thread(execute_redis, record["redis"])
        await clear_chroma(record["collections"], record["chroma"])
    except Exception as exc:
        await _audit(approval, "failed", record, self_approval, error=type(exc).__name__)
        raise
    return record


def _summary(record: dict) -> str:
    parts = [f"{s['kind']} {s['name']} ({s['count']})" for s in record["redis"]]
    parts += [f"chroma {c['name']} ({c['vectors']} vectors)" for c in record["chroma"]]
    return "Knowledge wipe done: " + ", ".join(parts)


async def execute_kb_wipe_action(approval: "Approval", session: "AsyncSession") -> None:
    """Wipe the KB for an approved gate. The durable audit comes first, then the comment and the commit."""
    if verified_decider(approval) is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the wipe is refused")
    self_approval = await _review_kb_wipe(approval, session)
    record = await _wipe(approval, self_approval)
    if not await _audit(approval, "success", record, self_approval):
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
    "KB_WIPE_DATABASES",
    "PROPOSED_BY",
    "execute_kb_wipe_action",
    "plan_kb_wipe",
    "propose_kb_wipe",
    "register_kb_wipe_action",
]
