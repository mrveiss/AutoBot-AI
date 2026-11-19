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

from services.kb_collection_delete_action import (
    BULK_DELETE,
    DELETE,
    CollectionOp,
    count_facts,
    plan_for,
    propose,
)
from services.kb_wipe_request import require_attributed_admin

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
) -> dict:
    requester = require_attributed_admin(current_user, "a knowledge collection deletion")
    plan = await plan_for(op, kb, cid, delete_facts)
    if plan is None:
        raise HTTPException(404, f"Collection not found: {cid}")
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


async def preview_collection_bulk_delete(kb, cid: str) -> dict:
    """Read only: what a bulk delete would remove, for a call without ``confirm``; 404 for an unknown collection."""
    facts = await count_facts(kb, cid)
    if facts is None:
        raise HTTPException(404, f"Collection not found: {cid}")
    return {
        "status": "preview",
        "collection_id": cid,
        "facts_in_collection": facts,
        "confirm_required": True,
        "message": f"Set confirm=true to propose deleting {facts} facts; nothing is deleted until a human approves",
    }
