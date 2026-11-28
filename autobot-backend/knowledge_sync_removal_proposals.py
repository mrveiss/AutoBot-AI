# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sync removals beyond a changed file's own chunks are PROPOSED, never applied (#20028, #17038).

Owner decision 2026-11-28 on #20028: the incremental sync deletes automatically only what it replaces
itself -- a changed file's own old chunks, created and tracked by the sync, verified unmodified, one audit
row per deletion (``knowledge_sync_replacement``, decision 2026-10-30). Every other removal is a proposal in
the approval queue, and a human's approval is what deletes:

* ``partial_tree``: tracked files missing while their directory remains;
* ``expired``: facts past their TTL. The file is re-indexed first, so a stale fact is refreshed, and the
  superseded facts are what is proposed;
* ``directory_missing``: tracked files whose whole directory is gone (a deliberate delete, or an unmounted
  tree: the sync cannot tell, so a person decides, #19701).

One open proposal per kind per project root (dedupe key ``scope``), so a repeated sync never stacks copies.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import TYPE_CHECKING, Any, Dict, Iterable, List

from fastapi import HTTPException

from autobot_shared.logging_manager import get_logger
from knowledge_sync_replacement import SYNC_AUDIT_ACTOR, _is_protected
from models.approval import Approval
from services.approval_execution import register_post_approval_action
from services.approval_gate_service import ApprovalGateService
from services.audit_logger import audit_log
from services.kb_cleanup_proposals import (
    cleanup_proposal,
    create_proposal_once,
    record_cleanup_outcome,
    record_cleanup_proposed,
    require_context,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route to the executor below.
ACTION = "kb_sync_removal"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "knowledge_sync_removal_proposals"
#: The dedupe key in the approval context: ``<kind>:<root digest>``.
SCOPE_KEY = "scope"

PARTIAL_TREE = "partial_tree"
EXPIRED = "expired"
DIRECTORY_MISSING = "directory_missing"
_REASONS = {
    PARTIAL_TREE: "their source files are missing while the directory they were in remains",
    EXPIRED: "they passed their time-to-live and the source was re-indexed, so a newer copy exists",
    DIRECTORY_MISSING: "the directory of their source files is gone (deleted, or a tree that is not mounted)",
}
_SERVICE_USER = {"username": SYNC_AUDIT_ACTOR}
_SAMPLE = 10


def _scope(kind: str, project_root: Any) -> str:
    return f"{kind}:{hashlib.sha256(str(project_root).encode('utf-8')).hexdigest()[:16]}"


async def live_fact_ids(kb: Any, fact_ids: Iterable[str]) -> List[str]:
    """The ids that still name a stored fact; a gone fact has nothing left to remove."""
    ids = list(dict.fromkeys(fact_ids))
    found = await asyncio.gather(*[asyncio.to_thread(kb.get_fact, fid) for fid in ids], return_exceptions=True)
    return [fid for fid, fact in zip(ids, found) if fact and not isinstance(fact, Exception)]


def _text(kind: str, entries: Dict[str, List[str]]) -> tuple[str, str]:
    total = sum(len(ids) for ids in entries.values())
    sample = "\n".join(f"- {path} ({len(ids)})" for path, ids in list(entries.items())[:_SAMPLE])
    more = len(entries) - _SAMPLE
    tail = f"\n- ... and {more} more source file(s)" if more > 0 else ""
    title = f"Remove {total} knowledge fact(s) from {len(entries)} synced source file(s)"
    return title, f"Proposed because {_REASONS[kind]}. Approving deletes exactly these facts:\n{sample}{tail}"


async def _create(
    service: ApprovalGateService, kind: str, scope: str, entries: Dict[str, List[str]], approval_id: uuid.UUID
) -> Approval:
    """The durable audit row first (no row, no proposal), then the pending approval it names."""
    await record_cleanup_proposed(
        approval_id, _SERVICE_USER, operation="knowledge.sync_removal_proposed", resource=f"kb-sync:{scope}"
    )
    title, description = _text(kind, entries)
    context = {
        "action": ACTION,
        "kind": kind,
        SCOPE_KEY: scope,
        "sources": entries,
        "fact_ids": [fid for ids in entries.values() for fid in ids],
    }
    return await service.create_approval(
        **cleanup_proposal(
            _SERVICE_USER, title=title, description=description, context=context, approval_id=approval_id
        )
    )


async def _propose_in_session(session: "AsyncSession", kind: str, entries: Dict[str, List[str]], scope: str) -> None:
    service = ApprovalGateService(session)
    await create_proposal_once(
        service,
        ACTION,
        SCOPE_KEY,
        scope,
        lambda approval_id: _create(service, kind, scope, entries, approval_id),
        current_user=_SERVICE_USER,
        resource=f"kb-sync:{scope}",
    )


async def propose_removal(kind: str, project_root: Any, entries: Dict[str, List[str]]) -> bool:
    """Propose removing *entries* (source path -> fact ids); True when a proposal is open for them.

    Never raises: a sync whose proposal could not be recorded has removed nothing, and the next run proposes
    again.
    """
    if not entries:
        return False
    from user_management.database import get_async_session_factory

    try:
        async with get_async_session_factory()() as session:
            await _propose_in_session(session, kind, entries, _scope(kind, project_root))
        return True
    except HTTPException as exc:
        logger.error("KB sync removal (%s) was not proposed: %s", kind, exc.detail)
    except Exception:
        logger.exception("KB sync removal (%s) was not proposed", kind)
    return False


async def propose_for_paths(
    kind: str, kb: Any, project_root: Any, file_metadata: Dict[str, Any], paths: List[str]
) -> int:
    """Propose removing the facts of tracked *paths*; returns how many facts were proposed.

    A fact another file still relies on stays (#20074). A path with no stored fact left is dropped from
    *file_metadata*: that is only the sync's own record, not a stored fact.
    """
    entries: Dict[str, List[str]] = {}
    for path in paths:
        meta = file_metadata.get(path)
        if meta is None:
            continue
        others = {f for p, m in file_metadata.items() if p != path for f in (*m.fact_ids, *m.shared_fact_ids)}
        live = await live_fact_ids(kb, [f for f in (*meta.fact_ids, *meta.shared_fact_ids) if f not in others])
        if live:
            entries[meta.relative_path] = live
        else:
            del file_metadata[path]
    if entries and await propose_removal(kind, project_root, entries):
        return sum(len(ids) for ids in entries.values())
    return 0


async def propose_replaced(kind: str, kb: Any, project_root: Any, prior: Dict[str, Any], replaced: List[str]) -> int:
    """Propose removing *replaced* ids, grouped under the *prior* metadata of the files that held them."""
    live = set(await live_fact_ids(kb, replaced))
    entries = {}
    for meta in prior.values():
        ids = [f for f in dict.fromkeys((*meta.fact_ids, *meta.shared_fact_ids)) if f in live]
        if ids:
            entries[meta.relative_path] = ids
    if entries and await propose_removal(kind, project_root, entries):
        return len(live)
    return 0


async def propose_expired_replaced(kb: Any, project_root: Any, prior: Dict[str, Any], replaced: List[str]) -> List[str]:
    """Propose the replaced facts of re-indexed *prior* (expired) files; return the rest, which may be deleted."""
    expired_ids = {fid for meta in prior.values() for fid in (*meta.fact_ids, *meta.shared_fact_ids)}
    mine = [fid for fid in replaced if fid in expired_ids]
    if mine:
        await propose_replaced(EXPIRED, kb, project_root, prior, mine)
    return [fid for fid in replaced if fid not in expired_ids]


async def _remove_one(kb: Any, fact_id: str, approval: Approval) -> str | None:
    """Delete one approved fact; ``None`` when it went, else why it stayed."""
    fact = await asyncio.to_thread(kb.get_fact, fact_id)
    if not fact:
        return "already gone"
    if _is_protected(fact.get("metadata") or {}):
        return "protected, kept"
    details = {
        "approval_id": str(approval.id),
        "proposed_by": SYNC_AUDIT_ACTOR,
        "kind": (approval.context or {}).get("kind"),
    }
    written = await audit_log(
        "knowledge.remove",
        user_id=approval.decided_by_user,
        resource=f"fact:{fact_id}",
        details=details,
        durable=True,
    )
    if not written:
        return "audit row not written, kept"
    result = await kb.delete_fact(fact_id)
    if isinstance(result, dict) and result.get("status") == "error":
        return str(result.get("message"))
    return None


async def execute_sync_removal(approval: Approval, session: "AsyncSession") -> None:
    """Delete exactly the facts an approved gate named, one audit row each, and record the outcome."""
    from knowledge_base import get_knowledge_base

    (fact_ids,) = require_context(approval, "fact_ids")
    kb = await get_knowledge_base()
    outcomes = [(fid, await _remove_one(kb, fid, approval)) for fid in fact_ids]
    kept = [f"{fid}: {why}" for fid, why in outcomes if why]
    removed = len(outcomes) - len(kept)
    await record_cleanup_outcome(
        approval,
        session,
        operation="knowledge.sync_removal",
        done=removed > 0 or not kept,
        resource=f"kb-sync:{(approval.context or {}).get(SCOPE_KEY)}",
        summary=f"Sync removal ({removed} of {len(outcomes)} facts deleted)",
        reason="; ".join(kept[:_SAMPLE]) or None,
    )


def register_sync_removal() -> None:
    """Idempotent. Server-only and admin-decided: this approves deleting stored knowledge."""
    register_post_approval_action(
        ACTION, execute_sync_removal, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )
