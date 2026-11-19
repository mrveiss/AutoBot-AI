# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Delete a knowledge collection, or the facts in one, only through an approved proposal (#21383, #17038).

``DELETE /collections/{id}`` and ``POST /collections/{id}/bulk-delete`` used to delete straight away, for any
admin caller, human or agent. They now only *propose* (``approval_type=destructive_action``, the same gate and
review as ``services.kb_wipe_action`` and ``services.claude_md_reindex_action``); the delete runs when a human
approves it in the Approvals inbox.

Two actions, one executor body. The proposal names the operation, the collection id and (for a collection delete)
whether the facts go too, plus a fact count for the approver, and NO id list. The executor takes the scope from the
approved context, refuses a proposal whose selector is not one this module builds, recomputes the fact count on the
server and refuses a count above the approved one. The knowledge base's own ``delete_collection`` and
``bulk_delete_collection_facts`` do the deleting, so the behaviour is theirs and not a second copy.

The paper trail comes first: a durable "intent" entry is committed before the delete, and no committed entry means
nothing is deleted; the outcome (completion or failure) is recorded after.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from autobot_shared.logging_manager import get_logger
from models.approval import Approval, ApprovalComment, ApprovalStatus, ApprovalType
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit.taxonomy import AuditAction
from services.audit_logger import AuditResult, audit_log
from services.kb_wipe_action import (
    CHANNEL_API,
    decision_details,
    refresh_pending_plan,
    review_kb_proposal,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

#: The one collection/fact id format; the collection routes validate with it too.
COLLECTION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
#: The production module that PROPOSES these actions (#17315).
PROPOSED_BY = "services.kb_collection_delete_action"
_WHAT = "the knowledge collection deletion"


@dataclass(frozen=True)
class CollectionOp:
    action: str  # the ``context["action"]`` value a proposal names to route here
    operation: str  # the knowledge-base method the executor runs
    title: str
    description: str
    audit: AuditAction
    refresh_audit: AuditAction


DELETE = CollectionOp(
    action="kb_collection_delete",
    operation="delete_collection",
    title="Delete a knowledge collection",
    description="Deletes one knowledge collection (its records); with delete_facts set, the facts in it too.",
    audit=AuditAction.KNOWLEDGE_COLLECTION_DELETE,
    refresh_audit=AuditAction.KNOWLEDGE_COLLECTION_DELETE_REFRESH,
)
BULK_DELETE = CollectionOp(
    action="kb_collection_bulk_delete",
    operation="bulk_delete_collection_facts",
    title="Delete every fact in a knowledge collection",
    description="Deletes every fact in one knowledge collection and empties it. The collection itself stays.",
    audit=AuditAction.KNOWLEDGE_COLLECTION_BULK_DELETE,
    refresh_audit=AuditAction.KNOWLEDGE_COLLECTION_BULK_DELETE_REFRESH,
)
OPS = (DELETE, BULK_DELETE)


def selector_for(op: CollectionOp, collection_id: str, delete_facts: bool = False) -> dict:
    """The scope a proposal names: the only shape the executor accepts."""
    selector: dict = {"operation": op.operation, "collection_id": collection_id}
    if op is DELETE:
        selector["delete_facts"] = bool(delete_facts)
    return selector


async def _kb():
    from knowledge_factory import get_knowledge_base_async

    kb = await get_knowledge_base_async()
    if kb is None:
        raise RuntimeError("the knowledge base is not initialised; nothing was deleted")
    return kb


async def count_collection_facts(kb, collection_id: str) -> int | None:
    """Facts in the collection now (the KB's own read-only preview); ``None`` when the collection does not exist."""
    preview = await kb.bulk_delete_collection_facts(collection_id=collection_id, confirm=False)
    return int(preview.get("facts_to_delete") or 0) if preview.get("success") else None


async def plan_collection_delete(op: CollectionOp, kb, collection_id: str, delete_facts: bool = False) -> dict | None:
    """Read only: the selector and the fact count the approver sees. ``None`` when the collection is not found."""
    facts = await count_collection_facts(kb, collection_id)
    return None if facts is None else {"selector": selector_for(op, collection_id, delete_facts), "facts": facts}


async def _pending_proposal(session: "AsyncSession", op: CollectionOp, selector: dict) -> "Approval | None":
    query = (
        select(Approval)
        .where(
            Approval.status == ApprovalStatus.PENDING.value,
            Approval.context["action"].astext == op.action,
        )
        .with_for_update()
    )
    pending = (await session.execute(query)).scalars().all()
    return next(
        (a for a in pending if ((a.context or {}).get("plan") or {}).get("selector") == selector),
        None,
    )


async def propose(session: "AsyncSession", op: CollectionOp, requested_by: str, plan: dict) -> "Approval":
    """Raise (or reuse, plan refreshed) the one pending #17038 proposal for this selector. Deletes nothing."""
    from services.approval_gate_service import ApprovalGateService

    selector = plan["selector"]
    lock = f"{op.action}:{selector['collection_id']}"
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": lock})
    if (pending := await _pending_proposal(session, op, selector)) is not None:
        await refresh_pending_plan(
            session,
            pending,
            requested_by,
            plan,
            what=_WHAT,
            audit_action=op.refresh_audit,
            count_labels={"facts": "facts"},
        )
        return pending
    context = {
        "action": op.action,
        "requested_by": requested_by,
        "channel": CHANNEL_API,
        "plan": plan,
    }
    return await ApprovalGateService(session).create_approval(
        title=op.title,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=f"{op.description} Collection: {selector['collection_id']!r}.",
        requested_by_agent=f"kb-collection-delete:{requested_by}",
        context=context,
    )


async def _review(approval: "Approval", session: "AsyncSession") -> bool:
    return await review_kb_proposal(approval, session, _WHAT)


def _require_approved(op: CollectionOp, approval: "Approval") -> None:
    if (approval.context or {}).get("action") != op.action or approval.status != ApprovalStatus.APPROVED.value:
        raise ValueError(f"approval {approval.id} is not an approved {op.action} proposal; the deletion is refused")


def _check_scope(op: CollectionOp, approval: "Approval") -> dict:
    """The approved selector, refused unless it is exactly one this module builds; the scope is never the client's."""
    plan = (approval.context or {}).get("plan")
    selector = plan.get("selector") if isinstance(plan, dict) else None
    cid = selector.get("collection_id") if isinstance(selector, dict) else None
    valid = isinstance(cid, str) and COLLECTION_ID_RE.match(cid) is not None
    if not valid or selector != selector_for(op, cid, (selector or {}).get("delete_facts", False)):
        raise ValueError(f"approval {approval.id} names a different selector; the deletion is refused")
    return selector


async def _audit(
    op: CollectionOp,
    approval: "Approval",
    result: AuditResult,
    self_approval: bool,
    **extra: object,
) -> bool:
    """Whether the durable entry was committed."""
    return await audit_log(
        op.audit.value,
        result=result,
        user_id=approval.decided_by_user,
        resource="knowledge_base",
        durable=True,
        details=decision_details(approval, self_approval, **extra),
    )


async def _refuse_more_than_approved(
    op: CollectionOp, approval: "Approval", selector: dict, self_ok: bool, found: int
) -> None:
    """Delete nothing when more facts are in scope now than the approver saw; fewer is fine."""
    approved = ((approval.context or {}).get("plan") or {}).get("facts")
    if isinstance(approved, int) and not isinstance(approved, bool) and found <= approved:
        return
    await _audit(
        op,
        approval,
        "failed",
        self_ok,
        selector=selector,
        phase="refused",
        approved=approved,
        found=found,
    )
    raise ValueError(f"approval {approval.id} approved {approved} facts but {found} are in scope; nothing deleted")


async def _run_delete(op: CollectionOp, kb, selector: dict) -> int:
    """Run the knowledge base's own delete; returns the number of facts deleted."""
    cid = selector["collection_id"]
    if op is DELETE:
        result = await kb.delete_collection(collection_id=cid, delete_facts=selector["delete_facts"])
    else:
        result = await kb.bulk_delete_collection_facts(collection_id=cid, confirm=True)
    if not result.get("success"):
        raise RuntimeError(f"the knowledge base refused the deletion: {result.get('message')}")
    return int(result.get("facts_deleted" if op is DELETE else "deleted_count") or 0)


async def _delete_and_audit(op: CollectionOp, approval: "Approval", kb, selector: dict, self_approval: bool) -> int:
    try:
        return await _run_delete(op, kb, selector)
    except Exception as exc:
        await _audit_failure(op, approval, self_approval, selector, exc)
        raise


async def _audit_failure(
    op: CollectionOp,
    approval: "Approval",
    self_ok: bool,
    selector: dict,
    exc: BaseException,
) -> None:
    """Record the failed outcome; never raises, so the deletion's own error stays the one that propagates."""
    try:
        if await _audit(
            op,
            approval,
            "failed",
            self_ok,
            selector=selector,
            phase="failure",
            error=type(exc).__name__,
        ):
            return
    except Exception:  # noqa: BLE001 -- logged below; it must not replace the original error
        logger.exception("%s: the failure audit for approval %s raised", op.action, approval.id)
        return
    logger.error("%s: the failure audit for approval %s was not written", op.action, approval.id)


async def execute(op: CollectionOp, approval: "Approval", session: "AsyncSession") -> None:
    """Delete the approved scope: intent entry first, then the delete, then the outcome."""
    _require_approved(op, approval)
    if verified_decider(approval) is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the deletion is refused")
    self_approval = await _review(approval, session)
    selector = _check_scope(op, approval)
    kb = await _kb()
    found = await count_collection_facts(kb, selector["collection_id"])
    if found is None:
        raise ValueError(f"approval {approval.id}: collection {selector['collection_id']!r} no longer exists")
    await _refuse_more_than_approved(op, approval, selector, self_approval, found)
    if not await _audit(
        op,
        approval,
        "attempted",
        self_approval,
        selector=selector,
        phase="intent",
        facts=found,
    ):
        raise RuntimeError(f"the audit entry for approval {approval.id} could not be written; nothing was deleted")
    deleted = await _delete_and_audit(op, approval, kb, selector, self_approval)
    if not await _audit(
        op,
        approval,
        "success",
        self_approval,
        selector=selector,
        phase="completion",
        deleted=deleted,
    ):
        raise RuntimeError(f"the deletion for approval {approval.id} ran but its audit record could not be written")
    suffix = " (self-approved by the only admin)." if self_approval else "."
    body = f"Ran {op.operation}: {deleted} facts deleted{suffix}"
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


async def execute_collection_delete_action(approval: "Approval", session: "AsyncSession") -> None:
    await execute(DELETE, approval, session)


async def execute_collection_bulk_delete_action(approval: "Approval", session: "AsyncSession") -> None:
    await execute(BULK_DELETE, approval, session)


def register_collection_delete_actions() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler. Server-only, admin-only."""
    handlers = {
        DELETE: execute_collection_delete_action,
        BULK_DELETE: execute_collection_bulk_delete_action,
    }
    for op, handler in handlers.items():
        register_post_approval_action(
            op.action,
            handler,
            proposed_by=PROPOSED_BY,
            server_only=True,
            admin_only=True,
            review=_review,
        )
