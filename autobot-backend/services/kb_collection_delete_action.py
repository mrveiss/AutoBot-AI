# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Delete a knowledge collection, or the facts in one, only through an approved proposal (#21383, #17038).

``DELETE /collections/{id}`` and ``POST /collections/{id}/bulk-delete`` used to delete straight away, for any
admin caller, human or agent. They now only *propose* (``approval_type=destructive_action``, the same gate and
review as ``services.kb_wipe_action`` and ``services.claude_md_reindex_action``); the delete runs when a human
approves it in the Approvals inbox.

Three actions, one executor body. The proposal names the operation, the collection id and (for a collection delete)
whether the facts go too, plus a fact count for the approver, and NO id list. The third action (#21886) deletes
exactly the facts a human selected in one collection: its selector carries those sorted fact ids, the only id
list a proposal holds; the executor deletes only those still members, never more than approved.
The executor takes the scope from the
approved context, refuses a proposal whose selector is not one this module builds, recomputes the fact count on the
server and refuses a count above the approved one. The knowledge base's own ``delete_collection`` and
``bulk_delete_collection_facts`` do the deleting, so the behaviour is theirs and not a second copy.

Identity and staleness. The plan records the collection's ``created_at`` and the executor refuses when it changed,
so a collection deleted and re-created under the same id after the approval is not deleted. Between the approval and
the execution there is no other window: the executor runs right after the approval commits, and an approval carries
no expiry of its own (``expires_at`` is unset on these proposals). The identity and the fact count travel into the
delete itself (``approved=``): the knowledge base checks them against the collection record and membership it reads
for that very delete, so a replacement created during the intent audit is refused. A replacement created inside the
knowledge base's own few awaited steps is not excluded: the store has no transaction across them (the same non-
atomic window the wipe documents). The plan also carries the collection ``name`` for the approver to read; it is
display only, never part of the selector and never used for scope. The "more than approved" refusal applies only
where facts are deleted (a bulk delete, or a collection delete with ``delete_facts``).

The paper trail comes first: a durable "intent" entry is committed before the delete, and no committed entry means
nothing is deleted; the outcome (completion or failure) is recorded after.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

from autobot_shared.logging_manager import get_logger
from knowledge.collections import NOT_FOUND
from models.approval import Approval, ApprovalComment, ApprovalType
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit.taxonomy import AuditAction
from services.audit_logger import AuditResult, audit_log
from services.kb_approved_delete import (
    Audit,
    pending_approval,
    refuse_more_than_approved,
    require_approved,
    run_audited_delete,
    write_audit,
)
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
#: Delete exactly the selected facts of one collection (#21886): the selector carries their sorted ids, the audit
#: entries are the bulk-delete ones (the selector in their details tells the two apart).
DOCUMENTS_DELETE = CollectionOp(
    action="kb_collection_documents_delete",
    operation="bulk_delete_collection_facts",
    title="Delete selected facts from a knowledge collection",
    description="Deletes the selected facts from one knowledge collection. The collection and its other facts stay.",
    audit=AuditAction.KNOWLEDGE_COLLECTION_BULK_DELETE,
    refresh_audit=AuditAction.KNOWLEDGE_COLLECTION_BULK_DELETE_REFRESH,
)
OPS = (DELETE, BULK_DELETE, DOCUMENTS_DELETE)


def selector_for(
    op: CollectionOp, collection_id: str, delete_facts: bool = False, fact_ids: list[str] | None = None
) -> dict:
    """The scope a proposal names: the only shape the executor accepts."""
    selector: dict = {"operation": op.operation, "collection_id": collection_id}
    if op is DELETE:
        selector["delete_facts"] = bool(delete_facts)
    if op is DOCUMENTS_DELETE:
        selector["fact_ids"] = sorted(set(fact_ids or ()))
    return selector


async def _kb():
    from knowledge_factory import get_knowledge_base_async

    kb = await get_knowledge_base_async()
    if kb is None:
        raise RuntimeError("the knowledge base is not initialised; nothing was deleted")
    return kb


def _is_missing(result: dict) -> bool:
    """Whether a failed KB answer is the structured not-found one (and not that the store failed)."""
    return result.get("code") == NOT_FOUND


async def collection_state(kb, collection_id: str, fact_ids: list[str] | None = None) -> tuple[dict, int] | None:
    """The collection record and its fact count now (read only); ``fact_ids`` counts only those facts' members.

    ``None`` only when the collection does not exist; any other failure (store unavailable) raises.
    """
    found = await kb.get_collection(collection_id=collection_id)
    if not found.get("success"):
        if _is_missing(found):
            return None
        raise RuntimeError(f"the knowledge base could not read the collection: {found.get('message')}")
    scope = {} if fact_ids is None else {"fact_ids": fact_ids}
    preview = await kb.bulk_delete_collection_facts(collection_id=collection_id, confirm=False, **scope)
    if not preview.get("success"):
        raise RuntimeError(f"the knowledge base could not count the facts: {preview.get('message')}")
    return (found.get("collection") or {}), int(preview.get("facts_to_delete") or 0)


async def count_collection_facts(kb, collection_id: str) -> int | None:
    """Facts in the collection now; ``None`` when the collection does not exist."""
    state = await collection_state(kb, collection_id)
    return None if state is None else state[1]


async def plan_collection_delete(
    op: CollectionOp, kb, collection_id: str, delete_facts: bool = False, fact_ids: list[str] | None = None
) -> dict | None:
    """Read only: what the approver sees. ``None`` when the collection is not found.

    ``created_at`` is the identity the executor re-checks; ``name`` is display only. For a selected-facts delete the
    selector names the selected ids, and ``facts`` counts those that are members now (the bound the executor holds).
    """
    state = await collection_state(kb, collection_id, fact_ids)
    if state is None:
        return None
    collection, facts = state
    return {
        "selector": selector_for(op, collection_id, delete_facts, fact_ids),
        "facts": facts,
        "created_at": collection.get("created_at"),
        "name": collection.get("name"),
    }


async def _pending_proposal(session: "AsyncSession", op: CollectionOp, selector: dict) -> "Approval | None":
    return await pending_approval(session, op.action, lambda ctx: (ctx.get("plan") or {}).get("selector") == selector)


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
    context = {"action": op.action, "requested_by": requested_by, "channel": CHANNEL_API, "plan": plan}
    return await ApprovalGateService(session).create_approval(
        title=op.title,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=f"{op.description} Collection: {plan.get('name') or selector['collection_id']!r}.",
        requested_by_agent=f"kb-collection-delete:{requested_by}",
        context=context,
    )


async def _review(approval: "Approval", session: "AsyncSession") -> bool:
    return await review_kb_proposal(approval, session, _WHAT)


def _valid_fact_ids(op: CollectionOp, selector: dict) -> bool:
    """A selected-facts delete names a non-empty list of well-formed fact ids; the other operations name none."""
    ids = selector.get("fact_ids")
    if op is not DOCUMENTS_DELETE:
        return ids is None
    return isinstance(ids, list) and bool(ids) and all(isinstance(i, str) and COLLECTION_ID_RE.match(i) for i in ids)


def _check_scope(op: CollectionOp, approval: "Approval") -> dict:
    """The approved selector, refused unless it is exactly one this module builds; the scope is never the client's."""
    plan = (approval.context or {}).get("plan")
    selector = plan.get("selector") if isinstance(plan, dict) else None
    cid = selector.get("collection_id") if isinstance(selector, dict) else None
    valid = isinstance(cid, str) and COLLECTION_ID_RE.match(cid) is not None and _valid_fact_ids(op, selector)
    if not valid or selector != selector_for(op, cid, selector.get("delete_facts", False), selector.get("fact_ids")):
        raise ValueError(f"approval {approval.id} names a different selector; the deletion is refused")
    return selector


def _auditor(op: CollectionOp, approval: "Approval", self_approval: bool, selector: dict) -> Audit:
    async def audit(result: AuditResult, details: dict) -> bool:
        merged = decision_details(approval, self_approval, selector=selector, **details)
        return await write_audit(audit_log, op.audit, approval, result, merged)

    return audit


def _approved_scope(approval: "Approval") -> dict:
    """The count and the identity the approver saw; the KB checks them against the very records it deletes."""
    plan = (approval.context or {}).get("plan") or {}
    return {"facts": plan.get("facts"), "created_at": plan.get("created_at")}


def _deletes_facts(op: CollectionOp, selector: dict) -> bool:
    """A bulk or selected-facts delete always deletes facts; a collection delete only when asked to."""
    return op is not DELETE or bool(selector.get("delete_facts"))


async def _refuse_recreated(approval: "Approval", audit: Audit, collection: dict) -> None:
    """Delete nothing when the collection is not the one that was approved (deleted and re-created under its id)."""
    approved = ((approval.context or {}).get("plan") or {}).get("created_at")
    if approved is not None and approved == collection.get("created_at"):
        return
    await audit(
        "failed",
        {"phase": "refused", "approved_created_at": approved, "found_created_at": collection.get("created_at")},
    )
    raise ValueError(
        f"approval {approval.id} names a collection that changed since it was approved; nothing was deleted"
    )


async def _run_delete(op: CollectionOp, kb, selector: dict, approved: dict) -> int:
    """Run the knowledge base's own delete; returns the number of facts deleted.

    ``approved`` bounds the membership the delete itself reads, so a fact added after the count check cannot be
    deleted with the approved ones: the knowledge base refuses (deleting nothing) when its own read is larger.
    """
    cid = selector["collection_id"]
    if op is DELETE:
        result = await kb.delete_collection(collection_id=cid, delete_facts=selector["delete_facts"], approved=approved)
    else:
        scope = {"fact_ids": selector["fact_ids"]} if op is DOCUMENTS_DELETE else {}
        result = await kb.bulk_delete_collection_facts(collection_id=cid, confirm=True, approved=approved, **scope)
    if not result.get("success"):
        raise RuntimeError(f"the knowledge base refused the deletion: {result.get('message')}")
    return int(result.get("facts_deleted" if op is DELETE else "deleted_count") or 0)


async def _guarded_state(op: CollectionOp, approval: "Approval", kb, selector: dict, audit: Audit) -> int:
    """The facts in scope now, after the identity and the count checks; refuses (deleting nothing) otherwise."""
    state = await collection_state(kb, selector["collection_id"], selector.get("fact_ids"))
    if state is None:
        raise ValueError(f"approval {approval.id}: collection {selector['collection_id']!r} no longer exists")
    await _refuse_recreated(approval, audit, state[0])
    if _deletes_facts(op, selector):
        await refuse_more_than_approved(
            audit,
            approval,
            state[1],
            count_key="facts",
            unit="facts",
            refused_details=lambda approved, found: {"approved": approved, "found": found},
        )
    return state[1]


async def execute(op: CollectionOp, approval: "Approval", session: "AsyncSession") -> None:
    """Delete the approved scope: intent entry first, then the delete, then the outcome."""
    require_approved(approval, op.action, "the deletion")
    if verified_decider(approval) is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the deletion is refused")
    self_approval = await _review(approval, session)
    selector = _check_scope(op, approval)
    kb, audit = await _kb(), _auditor(op, approval, self_approval, selector)
    facts = await _guarded_state(op, approval, kb, selector, audit)
    deleted = await run_audited_delete(
        approval,
        audit,
        what="the deletion",
        intent={"facts": facts},
        delete=lambda: _run_delete(op, kb, selector, _approved_scope(approval)),
        failure=lambda exc: {"error": type(exc).__name__},
        completion=lambda count: {"deleted": count},
        log=logger,
    )
    suffix = " (self-approved by the only admin)." if self_approval else "."
    body = f"Ran {op.operation}: {deleted} facts deleted{suffix}"
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


async def execute_collection_delete_action(approval: "Approval", session: "AsyncSession") -> None:
    await execute(DELETE, approval, session)


async def execute_collection_bulk_delete_action(approval: "Approval", session: "AsyncSession") -> None:
    await execute(BULK_DELETE, approval, session)


async def execute_collection_documents_delete_action(approval: "Approval", session: "AsyncSession") -> None:
    await execute(DOCUMENTS_DELETE, approval, session)


def register_collection_delete_actions() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler. Server-only, admin-only."""
    handlers = {
        DELETE: execute_collection_delete_action,
        BULK_DELETE: execute_collection_bulk_delete_action,
        DOCUMENTS_DELETE: execute_collection_documents_delete_action,
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
