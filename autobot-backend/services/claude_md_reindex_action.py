# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Delete the stale CLAUDE.md chunks only through an approved proposal (#21383, #17038).

``reindex_claude_md.sh`` used to delete every knowledge chunk titled as CLAUDE.md, straight from the shell.
That is a data deletion, so it is now only *proposed* (``approval_type=destructive_action``, the same gate and
review as ``services.kb_wipe_action``); the chunks are deleted when a human approves, and the re-index runs
afterwards from the script.

The proposal names WHAT is deleted: the chunk selector (the ``title`` field of ``doc:*`` hashes in the
``knowledge`` Redis database) and the search index those chunks belong to. It carries a count for the approver and
NO key list. The executor recomputes the keys on the server from the selector in the code, refuses a proposal whose
selector or index differs from the code's, and so never deletes anything a client named. The search index itself is
not dropped: its entries follow their hashes. Not atomic: a chunk written during the run survives.

The paper trail comes first: a durable "intent" entry is committed before the first delete, and no committed
entry means nothing is deleted; a failure partway records how many chunks were already gone.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from redis.exceptions import ResponseError
from sqlalchemy import select, text

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_utils import decode_redis_value
from knowledge.index_scope import kb_index_names
from models.approval import Approval, ApprovalComment, ApprovalStatus, ApprovalType
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit.taxonomy import AuditAction
from services.audit_logger import AuditResult, audit_log
from services.kb_wipe_action import CHANNEL_OPERATOR, decision_details, review_kb_proposal
from services.kb_wipe_redis import SCAN_BATCH, ClientFactory, default_client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "claude_md_reindex"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.claude_md_reindex_action"
PROPOSAL_TITLE = "Delete the stale CLAUDE.md knowledge chunks, then re-index"
DATABASE = "knowledge"
CHUNK_PREFIX = "doc:"
SELECTOR_FIELD = "title"
#: The title the re-index writes on every CLAUDE.md chunk; the selector, fixed in code.
SELECTOR_VALUE = "AutoBot Development Instructions & Project Reference"
_WHAT = "the CLAUDE.md chunk deletion"
PROPOSAL_DESCRIPTION = (
    f"Deletes the knowledge chunks whose {SELECTOR_FIELD!r} is {SELECTOR_VALUE!r} (keys under {CHUNK_PREFIX!r} in "
    f"the {DATABASE!r} database). Nothing else is touched. The CLAUDE.md re-index is run by the operator afterwards."
)


def _title(client, key: str) -> str | None:
    """The chunk's selector field; ``None`` for a key that is not a hash or has no such field."""
    try:
        value = client.hget(key, SELECTOR_FIELD)
    except ResponseError:  # a doc:* key of another type (version counters, host sets)
        return None
    return None if value is None else decode_redis_value(value)


def matching_chunk_keys(client) -> list[str]:
    """The chunk keys the selector matches right now. The only place the delete scope is computed."""
    keys = (decode_redis_value(k) for k in client.scan_iter(match=f"{CHUNK_PREFIX}*", count=SCAN_BATCH))
    return [key for key in keys if _title(client, key) == SELECTOR_VALUE]


def _selector() -> dict:
    return {"database": DATABASE, "prefix": CHUNK_PREFIX, "field": SELECTOR_FIELD, "value": SELECTOR_VALUE}


async def plan_claude_md_reindex(client_factory: ClientFactory = default_client) -> dict:
    """Read only: what the deletion would remove (selector, index, chunk count)."""
    keys = await asyncio.to_thread(lambda: matching_chunk_keys(client_factory(DATABASE)))
    return {"selector": _selector(), "indexes": list(kb_index_names()), "chunks": len(keys)}


async def _pending_proposal(session: "AsyncSession") -> "Approval | None":
    query = (
        select(Approval)
        .where(Approval.status == ApprovalStatus.PENDING.value, Approval.context["action"].astext == ACTION)
        .with_for_update()
    )
    return (await session.execute(query)).scalars().first()


async def propose_claude_md_reindex(session: "AsyncSession", requested_by: str, plan: dict) -> "Approval":
    """Raise (or reuse) the one pending #17038 proposal. Deletes nothing.

    An advisory lock held until the transaction commits serialises proposers. A pending proposal is reused as it
    is: the executor recomputes the chunks, so the count the approver saw is information, not the scope.
    """
    from services.approval_gate_service import ApprovalGateService

    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": ACTION})
    if (pending := await _pending_proposal(session)) is not None:
        return pending
    context = {"action": ACTION, "requested_by": requested_by, "channel": CHANNEL_OPERATOR, "plan": plan}
    return await ApprovalGateService(session).create_approval(
        title=PROPOSAL_TITLE,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=PROPOSAL_DESCRIPTION,
        requested_by_agent=f"claude-md-reindex:{requested_by}",
        context=context,
    )


async def _review(approval: "Approval", session: "AsyncSession") -> bool:
    return await review_kb_proposal(approval, session, _WHAT)


def _require_approved(approval: "Approval") -> None:
    if (approval.context or {}).get("action") != ACTION or approval.status != ApprovalStatus.APPROVED.value:
        raise ValueError(f"approval {approval.id} is not an approved {ACTION} proposal; the deletion is refused")


def _check_scope(approval: "Approval") -> None:
    """Refuse a proposal whose selector or index is not the code's: the scope is never taken from the client."""
    plan = (approval.context or {}).get("plan")
    if not isinstance(plan, dict) or plan.get("selector") != _selector():
        raise ValueError(f"approval {approval.id} names a different selector; the deletion is refused")
    if not set(plan.get("indexes") or []) <= set(kb_index_names()):
        raise ValueError(f"approval {approval.id} names an index the knowledge base does not own; refused")


async def _audit(approval: "Approval", result: AuditResult, self_approval: bool, **extra: object) -> bool:
    """Whether the durable entry was committed."""
    return await audit_log(
        AuditAction.KNOWLEDGE_CLAUDE_MD_REINDEX.value,
        result=result,
        user_id=approval.decided_by_user,
        resource="knowledge_base",
        durable=True,
        details=decision_details(approval, self_approval, selector=_selector(), **extra),
    )


def _delete_chunks(client, keys: list[str], deleted: list[int]) -> None:
    """Unlink *keys* in batches; ``deleted[0]`` is the running count, readable if a batch fails."""
    for start in range(0, len(keys), SCAN_BATCH):
        batch = keys[start : start + SCAN_BATCH]
        client.unlink(*batch)
        deleted[0] += len(batch)


async def _delete_and_audit(approval: "Approval", keys: list[str], self_approval: bool) -> int:
    deleted = [0]
    try:
        await asyncio.to_thread(_delete_chunks, default_client(DATABASE), keys, deleted)
    except Exception as exc:
        await _audit_failure(approval, self_approval, deleted[0], exc)
        raise
    return deleted[0]


async def _audit_failure(approval: "Approval", self_approval: bool, deleted: int, exc: BaseException) -> None:
    """Record the failed outcome; never raises, so the deletion's own error stays the one that propagates."""
    try:
        if await _audit(approval, "failed", self_approval, phase="failure", deleted=deleted, error=type(exc).__name__):
            return
    except Exception:  # noqa: BLE001 -- logged below; it must not replace the original error
        logger.exception("CLAUDE.md chunk deletion: the failure audit for approval %s raised", approval.id)
        return
    logger.error("CLAUDE.md chunk deletion: the failure audit for approval %s was not written", approval.id)


async def execute_claude_md_reindex_action(approval: "Approval", session: "AsyncSession") -> None:
    """Delete the selector's chunks for an approved gate: intent entry first, then the delete, then the outcome."""
    _require_approved(approval)
    if verified_decider(approval) is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the deletion is refused")
    self_approval = await _review(approval, session)
    _check_scope(approval)
    keys = await asyncio.to_thread(lambda: matching_chunk_keys(default_client(DATABASE)))
    if not await _audit(approval, "attempted", self_approval, phase="intent", chunks=len(keys)):
        raise RuntimeError(f"the audit entry for approval {approval.id} could not be written; nothing was deleted")
    deleted = await _delete_and_audit(approval, keys, self_approval)
    if not await _audit(approval, "success", self_approval, phase="completion", deleted=deleted):
        raise RuntimeError(f"the deletion for approval {approval.id} ran but its audit record could not be written")
    body = f"Deleted {deleted} CLAUDE.md chunks" + (" (self-approved by the only admin)." if self_approval else ".")
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


def register_claude_md_reindex_action() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler."""
    register_post_approval_action(
        ACTION,
        execute_claude_md_reindex_action,
        proposed_by=PROPOSED_BY,
        server_only=True,
        admin_only=True,
        review=_review,
    )


__all__ = [
    "ACTION",
    "PROPOSED_BY",
    "execute_claude_md_reindex_action",
    "matching_chunk_keys",
    "plan_claude_md_reindex",
    "propose_claude_md_reindex",
    "register_claude_md_reindex_action",
]
