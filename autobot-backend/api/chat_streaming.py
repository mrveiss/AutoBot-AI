# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSE streaming helpers for the chat endpoints (Issue #398), moved out of ``api/chat.py`` (#18430).

Both generators hand the AUTHENTICATED caller's role and scope (org, user) to the workflow manager. The scope is whose
AI lines are decided, so it must come from the session, never from the request's own ``context`` bag.
"""

import json

from autobot_shared.error_utils import safe_http_detail
from autobot_shared.logging_manager import get_logger
from autobot_shared.principal import resolve_principal_id

logger = get_logger(__name__)


def principal_scope(current_user: dict | None) -> dict:
    """The AUTHENTICATED principal's org and user, for the AI lines' scope (#18430)."""
    user = current_user or {}
    # #19241: the canonical claim order (#13688), shared with provider sign-in and the LLM principal.
    return {"org_id": user.get("org_id"), "user_id": resolve_principal_id(user)}


async def _stream_chat_workflow_messages(
    chat_workflow_manager,
    chat_id: str,
    message: str,
    context: dict,
    request_id: str,
    auth_role: str | None = None,
    auth_scope: dict | None = None,
):
    """Stream chat workflow messages as SSE events (Issue #398: extracted)."""
    try:
        logger.debug("[%s] Starting stream for chat_id=%s", request_id, chat_id)
        evt = {"type": "start", "session_id": chat_id, "request_id": request_id}
        yield f"data: {json.dumps(evt)}\n\n"

        logger.debug("[%s] Processing message: %s...", request_id, message[:50])
        message_count = 0
        async for msg in chat_workflow_manager.process_message_stream(
            session_id=chat_id, message=message, context=context, auth_role=auth_role, auth_scope=auth_scope
        ):
            message_count += 1
            msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
            yield f"data: {json.dumps(msg_data)}\n\n"

        logger.info("[%s] Stream complete: %d messages", request_id, message_count)
        yield f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n"

    except Exception as e:
        logger.error("[%s] Streaming error: %s", request_id, e, exc_info=True)
        evt = {"type": "error", "content": safe_http_detail(e, "stream_error"), "request_id": request_id}
        yield f"data: {json.dumps(evt)}\n\n"


async def _stream_direct_response(
    chat_workflow_manager,
    chat_id: str,
    message: str,
    remember_choice: bool,
    request_id: str,
    auth_role: str | None = None,
    auth_scope: dict | None = None,
):
    """Stream direct response for approvals/denials (Issue #398: extracted)."""
    try:
        start_evt = {"type": "start", "session_id": chat_id, "request_id": request_id}
        yield f"data: {json.dumps(start_evt)}\n\n"

        async for msg in chat_workflow_manager.process_message_stream(
            session_id=chat_id,
            message=message,
            context={"remember_choice": remember_choice},
            auth_role=auth_role,
            auth_scope=auth_scope,
        ):
            msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
            yield f"data: {json.dumps(msg_data)}\n\n"

        yield f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n"

    except Exception as e:
        logger.error("[%s] Direct response streaming error: %s", request_id, e, exc_info=True)
        error_data = {
            "type": "error",
            "content": "Error processing command approval",
            "request_id": request_id,
        }
        yield f"data: {json.dumps(error_data)}\n\n"
