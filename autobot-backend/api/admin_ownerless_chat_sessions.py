# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: report ownerless chat sessions and PROPOSE an owner for one (#20030).

Endpoints:
    GET  /api/admin/ownerless-chat-sessions           read only -- ids and a count, no content
    POST /api/admin/ownerless-chat-sessions/requests  PROPOSE an owner -- creates a PENDING approval

Neither route writes an owner. Nothing runs until a human approves it in the Approvals inbox, and it is
never auto-approved (#17038). The executor lives in ``services.chat_session_owner_action``.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_ownerless_chat_sessions import (
    OwnerlessChatSessionRequest,
    OwnerlessChatSessionRequestResponse,
    OwnerlessChatSessionsReport,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from models.approval import ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.chat_session_owner_action import (
    ACTION,
    active_user_id,
    ownerless_report,
    register_owner_assign_action,
)
from utils.chat_utils import get_chat_history_manager

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])

# Registered at this router's import time so the executor exists before any approve().
register_owner_assign_action()


@router.get("/ownerless-chat-sessions", response_model=OwnerlessChatSessionsReport)
async def ownerless_chat_sessions(request: Request) -> OwnerlessChatSessionsReport:
    """Read only: which sessions record no owner."""
    ownerless, unreadable = await ownerless_report(get_chat_history_manager(request))
    return OwnerlessChatSessionsReport(count=len(ownerless), session_ids=ownerless, unreadable=unreadable)


@router.post(
    "/ownerless-chat-sessions/requests",
    response_model=OwnerlessChatSessionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_chat_session_owner(
    body: OwnerlessChatSessionRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OwnerlessChatSessionRequestResponse:
    """Propose an owner -- a request, not an execution. Refused unless the session is ownerless and the user exists."""
    requester = current_user.get("id") or current_user.get("user_id")  # as the approve route reads the decider
    if not requester:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The proposal cannot be attributed to a verified user")
    ownerless, _ = await ownerless_report(get_chat_history_manager(request))
    if body.session_id not in ownerless:
        raise HTTPException(status.HTTP_409_CONFLICT, "That session is not in the ownerless report")
    if await active_user_id(session, body.owner) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That owner is not an active user")
    approval = await ApprovalGateService(session).create_approval(
        title=f"Give chat session {body.session_id} to {body.owner}",
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description="This session has no owner. Approving lets the named user read everything in it (#20025).",
        requested_by_agent=f"chat-session-owner:{requester}",
        context={
            "action": ACTION,
            "session_id": body.session_id,
            "owner": body.owner,
        },
    )
    return OwnerlessChatSessionRequestResponse(approval_id=str(approval.id), status=approval.status, action=ACTION)
