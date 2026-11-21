# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Assign an Unassigned chat to a company: the only way an existing chat gets one (#21997, #16905).

Nothing re-tags a chat on its own (no migration, no agent, no metadata merge: ``company_id`` is a
server-controlled key). A person who owns the chat names a company they may act in; the change is written between a
durable ``attempted`` audit row and its outcome row (``security.session_share_audit.audited_change``, the share
pattern) and a chat that already has a company is refused, so an assignment is made once and is never silently moved.
The owner-only gate is ``validate_session_owner`` (#21898): a participant, an org admin and an administrator are
refused exactly as an outsider is.
"""

import uuid
from typing import Dict

from fastapi import APIRouter, Depends, Request

from api.chat_session_sharing import validate_session_owner
from api.schemas_chat_company import SessionCompanyAssign, SessionCompanyAssignData
from api.schemas_common import DataResponse
from api.session_events import publish_session_updated
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_refusal import fixed_refusal
from security import session_shares
from security.session_company import (
    company_exists,
    company_of_session,
    may_act_in_company,
)
from security.session_share_audit import ShareAuditError, audited_change
from utils.chat_utils import (
    create_chat_response,
    generate_request_id,
    get_chat_history_manager,
)

router = APIRouter(tags=["chat-sessions"])


async def _require_assignable(request: Request, session_id: str, company_id: uuid.UUID, user: dict) -> None:
    """Refuse (canonical) an unknown chat, an assigned one, a company the caller may not act in or a made-up one."""
    if await get_chat_history_manager(request).get_session(session_id) is None:
        raise fixed_refusal(404)
    if await company_of_session(request, session_id):
        raise fixed_refusal(409)
    if not await may_act_in_company(company_id, user):
        raise fixed_refusal(403)
    if not await company_exists(company_id):
        raise fixed_refusal(404)


@router.post(
    "/chat/sessions/{session_id}/company",
    response_model=DataResponse[SessionCompanyAssignData],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="assign_session_company",
    error_code_prefix="CHAT_SESSIONS",
)
async def assign_session_company(
    session_id: str,
    body: SessionCompanyAssign,
    request: Request,
    ownership: Dict = Depends(validate_session_owner),
):
    """The owner assigns an Unassigned chat to a company; audited, once, never moved (#21997)."""
    from api.chat_sessions import _validate_session_id_or_raise, log_request_context

    request_id = generate_request_id()
    log_request_context(request, "assign_session_company", request_id)
    _validate_session_id_or_raise(session_id)
    user = ownership.get("user_data") or {}
    await _require_assignable(request, session_id, body.company_id, user)
    company = str(body.company_id)
    manager = get_chat_history_manager(request)
    try:
        changed = await audited_change(
            "assign_company",
            session_shares.audit_actor(request, user),
            session_id,
            [],
            lambda: manager.update_session_metadata(session_id, {"company_id": company}),
            details={"company_id": company},
        )
    except ShareAuditError:
        raise fixed_refusal(503) from None  # no audit record, no change
    if not changed:
        raise fixed_refusal(503)
    await publish_session_updated(session_id, {"companyId": company})
    return create_chat_response(
        data={"session_id": session_id, "company_id": company},
        message="Session assigned to the company",
        request_id=request_id,
    )
