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
from sqlalchemy import text

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_utils import decode_redis_value
from knowledge.index_scope import kb_index_names
from models.approval import Approval, ApprovalComment, ApprovalType
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit.taxonomy import AuditAction
from services.audit_logger import AuditResult, audit_log
from services.kb_approved_delete import (
    pending_approval,
    refuse_more_than_approved,
    require_approved,
    run_audited_delete,
    write_audit,
)
from services.kb_wipe_action import CHANNEL_OPERATOR, decision_details, refresh_pending_plan, review_kb_proposal
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
#: The second field: the re-index writes this source on every CLAUDE.md chunk, so a same-titled document of another
#: source is not touched.
SOURCE_FIELD = "source"
SOURCE_VALUE = "autobot_docs"
#: The title the re-index writes on every CLAUDE.md chunk; the selector, fixed in code.
SELECTOR_VALUE = "AutoBot Development Instructions & Project Reference"
_WHAT = "the CLAUDE.md chunk deletion"
PROPOSAL_DESCRIPTION = (
    f"Deletes the knowledge chunks whose {SELECTOR_FIELD!r} is {SELECTOR_VALUE!r} and {SOURCE_FIELD!r} is "
    f"{SOURCE_VALUE!r} (keys under {CHUNK_PREFIX!r} in "
    f"the {DATABASE!r} database). Nothing else is touched. The CLAUDE.md re-index is run by the operator afterwards."
)


def _field(client, key: str, field: str) -> str | None:
    """A chunk's field; ``None`` for a key that is not a hash or has no such field."""
    try:
        value = client.hget(key, field)
    except ResponseError:  # a doc:* key of another type (version counters, host sets)
        return None
    return None if value is None else decode_redis_value(value)


def _is_claude_md_chunk(client, key: str) -> bool:
    return _field(client, key, SELECTOR_FIELD) == SELECTOR_VALUE and _field(client, key, SOURCE_FIELD) == SOURCE_VALUE


def matching_chunk_keys(client) -> list[str]:
    """The chunk keys the selector matches right now. The only place the delete scope is computed."""
    keys = (decode_redis_value(k) for k in client.scan_iter(match=f"{CHUNK_PREFIX}*", count=SCAN_BATCH))
    return [key for key in keys if _is_claude_md_chunk(client, key)]


def _selector() -> dict:
    return {
        "database": DATABASE,
        "prefix": CHUNK_PREFIX,
        "field": SELECTOR_FIELD,
        "value": SELECTOR_VALUE,
        "source_field": SOURCE_FIELD,
        "source_value": SOURCE_VALUE,
    }


async def plan_claude_md_reindex(client_factory: ClientFactory = default_client) -> dict:
    """Read only: what the deletion would remove (selector, index, chunk count)."""
    keys = await asyncio.to_thread(lambda: matching_chunk_keys(client_factory(DATABASE)))
    return {"selector": _selector(), "indexes": list(kb_index_names()), "chunks": len(keys)}


async def _pending_proposal(session: "AsyncSession") -> "Approval | None":
    return await pending_approval(session, ACTION)


async def propose_claude_md_reindex(session: "AsyncSession", requested_by: str, plan: dict) -> "Approval":
    """Raise (or reuse) the one pending #17038 proposal. Deletes nothing.

    An advisory lock held until the transaction commits serialises proposers. A pending proposal is reused with its
    plan refreshed (durably audited, the refresher counted as a proposer), so the count the approver sees is current.
    """
    from services.approval_gate_service import ApprovalGateService

    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": ACTION})
    if (pending := await _pending_proposal(session)) is not None:
        await refresh_pending_plan(
            session,
            pending,
            requested_by,
            plan,
            what=_WHAT,
            audit_action=AuditAction.KNOWLEDGE_CLAUDE_MD_REINDEX_REFRESH,
            count_labels={"chunks": "chunks"},
        )
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
    require_approved(approval, ACTION, "the deletion")


def _check_scope(approval: "Approval") -> None:
    """Refuse a proposal whose selector or index is not the code's: the scope is never taken from the client."""
    plan = (approval.context or {}).get("plan")
    if not isinstance(plan, dict) or plan.get("selector") != _selector():
        raise ValueError(f"approval {approval.id} names a different selector; the deletion is refused")
    if not set(plan.get("indexes") or []) <= set(kb_index_names()):
        raise ValueError(f"approval {approval.id} names an index the knowledge base does not own; refused")


async def _audit(approval: "Approval", result: AuditResult, self_approval: bool, **extra: object) -> bool:
    """Whether the durable entry was committed."""
    details = decision_details(approval, self_approval, selector=_selector(), **extra)
    return await write_audit(audit_log, AuditAction.KNOWLEDGE_CLAUDE_MD_REINDEX, approval, result, details)


def _delete_chunks(client, keys: list[str], deleted: list[int]) -> None:
    """Unlink *keys* in batches; ``deleted[0]`` is the running count, readable if a batch fails."""
    for start in range(0, len(keys), SCAN_BATCH):
        batch = keys[start : start + SCAN_BATCH]
        client.unlink(*batch)
        deleted[0] += len(batch)


async def _delete_all(keys: list[str], deleted: list[int]) -> int:
    await asyncio.to_thread(_delete_chunks, default_client(DATABASE), keys, deleted)
    return deleted[0]


async def _refuse_then_delete(approval: "Approval", self_approval: bool, keys: list[str]) -> int:
    """Refuse a count above the approved one, then the audited delete; returns the number of chunks deleted."""

    async def audit(result: AuditResult, details: dict) -> bool:
        return await _audit(approval, result, self_approval, **details)

    await refuse_more_than_approved(
        audit,
        approval,
        len(keys),
        count_key="chunks",
        unit="chunks",
        refused_details=lambda approved, found: {"approved_chunks": approved, "found_chunks": found},
    )
    deleted = [0]  # the running count, readable if a batch fails
    return await run_audited_delete(
        approval,
        audit,
        what="the deletion",
        intent={"chunks": len(keys)},
        delete=lambda: _delete_all(keys, deleted),
        failure=lambda exc: {"deleted": deleted[0], "error": type(exc).__name__},
        completion=lambda count: {"deleted": count},
        log=logger,
    )


async def execute_claude_md_reindex_action(approval: "Approval", session: "AsyncSession") -> None:
    """Delete the selector's chunks for an approved gate: intent entry first, then the delete, then the outcome."""
    _require_approved(approval)
    if verified_decider(approval) is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the deletion is refused")
    self_approval = await _review(approval, session)
    _check_scope(approval)
    keys = await asyncio.to_thread(lambda: matching_chunk_keys(default_client(DATABASE)))
    deleted = await _refuse_then_delete(approval, self_approval, keys)
    suffix = " (self-approved by the only admin)." if self_approval else "."
    body = f"Deleted {deleted} CLAUDE.md chunks{suffix}"
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
