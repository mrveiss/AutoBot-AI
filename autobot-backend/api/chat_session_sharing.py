# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Share, list and unshare a chat's participants: owner only (#689, #18890).

Its own router because ``api/chat_sessions.py`` is at its recorded size ceiling; that module includes it, and
this one reaches back into it lazily (a top-level import would be circular). Every route runs
``validate_session_ownership`` and then ``require_owner``: only the reasons in ``OWNER_REASONS`` pass, so a
participant, an org admin and a ``log_only`` pass-through are refused exactly as an outsider is.
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_chat import SessionShareData, SessionShareRequest
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


def require_owner(ownership: Dict) -> None:
    """Allowlist: anything but an owner-equivalent reason is refused like an outsider, so nothing leaks."""
    if ownership.get("reason") not in session_shares.OWNER_REASONS:
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
    require_owner(ownership)
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

    require_owner(ownership)

    validator = SessionOwnershipValidator(await get_redis_client(async_client=True, database="main"))
    removed = await validator.unshare_session(
        session_id, user_id, session_shares.audit_actor(request, ownership.get("user_data"))
    )

    return create_chat_response(
        data={"session_id": session_id, "user_id": user_id, "removed": removed},
        message="Session unshared" if removed else "Session was not shared with that user",
        request_id=request_id,
    )


async def _share_session_facts(
    request: Request,
    session_id: str,
    share_with: list[str],
    shared_by: str,
    knowledge_facts: list[str] | None,
) -> Dict:
    """Share KB facts from a session with other users (#689)."""
    kb_manager = getattr(request.app.state, "kb_manager", None)
    if not kb_manager:
        return {"shared_count": 0, "errors": ["KB manager unavailable"]}
    fact_ids = knowledge_facts or await kb_manager.get_facts_by_session(session_id)
    if not fact_ids:
        return {"shared_count": 0, "errors": []}
    return await kb_manager.share_facts(fact_ids, share_with, shared_by)


@router.post("/chat/sessions/{session_id}/share", response_model=DataResponse[SessionShareData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="share_session",
    error_code_prefix="CHAT_SESSIONS",
)
async def share_session(
    session_id: str,
    share_data: SessionShareRequest,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """Owner shares a conversation with other users, optionally including KB facts (#689, #18890)."""
    request_id = generate_request_id()
    _check_request(request, "share_session", request_id, session_id)
    require_owner(ownership)

    actor = session_shares.audit_actor(request, ownership.get("user_data"))
    validator = SessionOwnershipValidator(await get_redis_client(async_client=True, database="main"))
    if not await validator.share_session(session_id, share_data.share_with, actor["username"], actor):
        raise HTTPException(status_code=500, detail="Session could not be shared")

    facts_result = None
    if share_data.include_knowledge:
        facts_result = await _share_session_facts(
            request, session_id, share_data.share_with, actor["username"], share_data.knowledge_facts
        )
    return create_chat_response(
        data={
            "session_id": session_id,
            "shared_with": share_data.share_with,
            "include_knowledge": share_data.include_knowledge,
            "facts_shared": facts_result,
        },
        message="Session shared successfully",
        request_id=request_id,
    )
