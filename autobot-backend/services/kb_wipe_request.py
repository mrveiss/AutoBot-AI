# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one way a product route asks for a knowledge wipe: it proposes, it never deletes (#21048, #17038).

Every route that used to empty the knowledge base (the admin route, ``POST /knowledge_base/clear_all`` and
the MCP vector ``flush`` operation) calls :func:`request_kb_wipe`, so the same operation behaves the same on
every route: only an admin who is a user may ask, the answer is the pending approval's reference, and the
deletion itself runs only after a human approves it (``services.kb_wipe_action``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from autobot_shared.approval_four_eyes import requester_id
from autobot_shared.auth.permissions import is_admin_role
from services.kb_wipe_action import ACTION, plan_kb_wipe, propose_kb_wipe

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _refuse(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


async def request_kb_wipe(current_user: dict, session: "AsyncSession") -> dict:
    """Propose (or reuse) the pending wipe approval for an admin user and return its reference. Deletes nothing.

    403 for a caller that is not an admin, or whose id is not a user id (a service key or a run token): the
    proposal must name a person, because the approver is checked against that person (four eyes).
    """
    if not is_admin_role(current_user.get("role")):
        raise _refuse("Requesting a knowledge wipe needs the admin role")
    requester = current_user.get("id") or current_user.get("user_id")
    if not requester:
        raise _refuse("The proposal cannot be attributed to a verified user")
    if requester_id(str(requester)) is None:  # refused before any plan is read or proposal row exists
        raise _refuse("The proposal needs a requester that is a user id")
    approval = await propose_kb_wipe(session, str(requester), await plan_kb_wipe())
    return {"approval_id": str(approval.id), "status": approval.status, "action": ACTION}


async def request_vector_flush(current_user: dict, session: "AsyncSession") -> dict:
    """The MCP ``flush`` operation: a wipe PROPOSAL in the MCP answer shape; no database is flushed."""
    try:
        proposal = await request_kb_wipe(current_user, session)
    except HTTPException as refused:
        return {"success": False, "operation": "flush", "error": str(refused.detail)}
    return {"success": True, "operation": "flush", "message": "Wipe requested; awaiting approval", **proposal}
