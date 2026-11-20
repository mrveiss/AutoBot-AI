# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unshare a chat: the owner removes a participant (#18890).

Its own router because ``api/chat_sessions.py`` is at its recorded size ceiling; that module includes it, and
this one reaches back into it lazily (a top-level import would be circular). It sits beside
``POST /chat/sessions/{id}/share`` and runs the same ``validate_session_ownership`` dependency.
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_chat_unshare import SessionParticipantsData, SessionUnshareData
from api.schemas_common import DataResponse
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import get_redis_client
from security import session_shares
from security.session_ownership import SessionOwnershipValidator, validate_session_ownership
from utils.chat_utils import create_chat_response, generate_request_id

router = APIRouter(tags=["chat-sessions"])


#: The refusal a non-owner gets on share/unshare alike; identical for an outsider and a participant.
_REFUSAL = "You do not have permission to access this conversation"


def _check_request(request: Request, endpoint: str, request_id: str, session_id: str) -> None:
    from api.chat_sessions import _validate_session_id_or_raise, log_request_context

    log_request_context(request, endpoint, request_id)
    _validate_session_id_or_raise(session_id)


def _require_owner(ownership: Dict) -> None:
    """A participant is not the owner: refused exactly as an outsider is, so the share does not leak."""
    if ownership.get("reason") == "shared_access":
        raise HTTPException(status_code=403, detail=_REFUSAL)


@router.get("/chat/sessions/{session_id}/share", response_model=DataResponse[SessionParticipantsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_session_participants",
    error_code_prefix="CHAT_SESSIONS",
)
async def list_session_participants(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """Who the owner has shared this conversation with, from the system of record (#18890)."""
    request_id = generate_request_id()
    _check_request(request, "list_session_participants", request_id, session_id)
    _require_owner(ownership)
    participants = sorted(await session_shares.durable_participants(session_id))
    return create_chat_response(
        data={"session_id": session_id, "participants": participants}, message="OK", request_id=request_id
    )


@router.delete("/chat/sessions/{session_id}/share/{user_id}", response_model=DataResponse[SessionUnshareData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unshare_session",
    error_code_prefix="CHAT_SESSIONS",
)
async def unshare_session(
    session_id: str,
    user_id: str,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """Owner removes a participant from a shared conversation; their access ends at once (#18890)."""
    request_id = generate_request_id()
    _check_request(request, "unshare_session", request_id, session_id)

    _require_owner(ownership)

    validator = SessionOwnershipValidator(await get_redis_client(async_client=True, database="main"))
    unshared_by = ownership.get("user_data", {}).get("username", "unknown")
    removed = await validator.unshare_session(session_id, user_id, unshared_by)

    return create_chat_response(
        data={"session_id": session_id, "user_id": user_id, "removed": removed},
        message="Session unshared" if removed else "Session was not shared with that user",
        request_id=request_id,
    )
