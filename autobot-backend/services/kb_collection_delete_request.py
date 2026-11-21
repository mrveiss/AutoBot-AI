# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one way a collection route asks for a knowledge delete: it proposes, it never deletes (#21383, #17038).

``DELETE /collections/{id}`` and ``POST /collections/{id}/bulk-delete`` call these for every caller, human or
agent. The answer is the pending approval's reference; the deletion itself runs only after a human approves it
(``services.kb_collection_delete_action``). Same attribution rule as the wipe: an admin who is a user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from pydantic import BaseModel

from autobot_shared.auth.permissions import is_admin_role
from services.kb_collection_delete_action import (
    BULK_DELETE,
    COLLECTION_ID_RE,
    DELETE,
    DOCUMENTS_DELETE,
    CollectionOp,
    count_collection_facts,
    plan_collection_delete,
    propose,
)
from services.kb_wipe_request import require_human_requester

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeCollectionDeleteProposal(BaseModel):
    """Answer of the two collection delete routes: a proposal (or, without confirm, a read-only preview)."""

    status: str
    collection_id: str
    facts_in_collection: int
    approval_id: str | None = None
    approval_status: str | None = None
    action: str | None = None
    confirm_required: bool = False
    message: str


async def _propose(
    op: CollectionOp,
    kb,
    current_user: dict,
    session: "AsyncSession",
    cid: str,
    delete_facts: bool,
    fact_ids: list[str] | None = None,
) -> dict:
    if not is_admin_role(current_user.get("role")):
        raise HTTPException(403, "Requesting a knowledge collection deletion needs the admin role")
    requester = require_human_requester(current_user)
    plan = await plan_collection_delete(op, kb, cid, delete_facts, fact_ids)
    if plan is None:
        raise HTTPException(404, f"Collection not found: {cid}")
    if fact_ids is not None and not plan["facts"]:
        raise HTTPException(404, "None of the selected facts are in this collection; nothing was proposed")
    approval = await propose(session, op, requester, plan)
    return {
        "status": "pending_approval",
        "collection_id": cid,
        "facts_in_collection": plan["facts"],
        "approval_id": str(approval.id),
        "approval_status": approval.status,
        "action": op.action,
        "message": "Deletion proposed; nothing is deleted until a human approves it in the Approvals inbox",
    }


async def request_collection_delete(kb, current_user: dict, session: "AsyncSession", cid: str, delete_facts: bool):
    """Propose deleting a collection (and its facts when asked). Deletes nothing."""
    return await _propose(DELETE, kb, current_user, session, cid, delete_facts)


async def request_collection_bulk_delete(kb, current_user: dict, session: "AsyncSession", cid: str) -> dict:
    """Propose deleting every fact in a collection. Deletes nothing."""
    return await _propose(BULK_DELETE, kb, current_user, session, cid, False)


def _selected_ids(fact_ids: list[str]) -> list[str]:
    """The selected ids, de-duplicated and sorted; 400 for one that is not a well-formed fact id."""
    if any(COLLECTION_ID_RE.match(i) is None for i in fact_ids):
        raise HTTPException(400, "Invalid fact id format: only alphanumeric, hyphens, underscores")
    return sorted(set(fact_ids))


async def request_collection_documents_delete(
    kb, current_user: dict, session: "AsyncSession", cid: str, fact_ids: list[str]
) -> dict:
    """Propose deleting exactly the selected facts of one collection. Deletes nothing (#21886)."""
    return await _propose(DOCUMENTS_DELETE, kb, current_user, session, cid, False, _selected_ids(fact_ids))


async def preview_collection_bulk_delete(kb, cid: str) -> dict:
    """Read only: what a bulk delete would remove, for a call without ``confirm``; 404 for an unknown collection."""
    facts = await count_collection_facts(kb, cid)
    if facts is None:
        raise HTTPException(404, f"Collection not found: {cid}")
    return {
        "status": "preview",
        "collection_id": cid,
        "facts_in_collection": facts,
        "confirm_required": True,
        "message": f"Set confirm=true to propose deleting {facts} facts; nothing is deleted until a human approves",
    }
