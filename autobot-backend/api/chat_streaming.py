# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSE streaming helpers for the chat endpoints (Issue #398), moved out of ``api/chat.py`` (#18430).

Both generators hand the AUTHENTICATED caller's role and scope (org, user) to the workflow manager. The scope is whose
AI lines are decided, so it must come from the session, never from the request's own ``context`` bag.
"""

import json

from fastapi import HTTPException

from autobot_shared.error_utils import safe_http_detail
from autobot_shared.logging_manager import get_logger
from autobot_shared.principal import resolve_principal_id

logger = get_logger(__name__)


def principal_scope(current_user: dict | None) -> dict:
    """The AUTHENTICATED principal's org and user, for the AI lines' scope (#18430)."""
    user = current_user or {}
    # #19241: the canonical claim order (#13688), shared with provider sign-in and the LLM principal.
    return {"org_id": user.get("org_id"), "user_id": resolve_principal_id(user)}


async def attachments_allowed(chat_id: str, current_user: dict | None, request) -> bool:
    """Whether the STRICT session posture passes: a global admin, or the recorded owner by username (#20195).

    The one validator (``security.session_posture.validate_strict``), not a copy: no shared-session grant, no org
    admin, no ``log_only`` pass. Any refusal or failure to learn the owner is False; a session the posture would
    merely claim (``legacy_unowned``) has no files of the caller's to attach.
    """
    from security.session_posture import validate_strict

    try:
        decision = await validate_strict(chat_id, current_user or {}, request)
    except HTTPException as exc:
        logger.info("Attachments not read for chat %s...: strict posture refused (%s)", chat_id[:8], exc.status_code)
        return False
    return decision.get("reason") != "legacy_unowned"


async def resume_attachment_verdict(manager, chat_id: str, current_user: dict | None, request) -> bool:
    """This resume request's STRICT verdict; a caller failing it cannot resume an attachment turn or chat (#20195).

    The refusal is a 404, as for a foreign conversation, and nothing resumes. An unreadable checkpoint or durable
    mark is refused too. An ordinary turn keeps the default ownership posture the route already applied.

    A chat with no recorded owner is a defect nobody claims (#20025): a global admin passes STRICT and can resume;
    any other user sees the same 404 as for a foreign chat, so that turn waits for an admin rather than being
    approvable by a user who cannot be shown to own it.
    """
    from chat_workflow.attachment_context import checkpoint_carries_floor
    from chat_workflow.attachment_floor import chat_used_attachment

    if await attachments_allowed(chat_id, current_user, request):
        return True
    try:
        carries = await checkpoint_carries_floor(manager, chat_id)
    except Exception as exc:  # noqa: BLE001 -- cannot tell an ordinary turn from an attachment one: refuse
        logger.warning("Resume refused for chat %s...: checkpoint unreadable (%s)", chat_id[:8], type(exc).__name__)
        carries = True
    # A checkpoint from before the chat was marked carries no stamp: the durable mark decides too (unreadable: True).
    carries = carries or await chat_used_attachment(chat_id)
    if carries:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return False


async def attach_scope(current_user: dict | None, chat_id: str, request, context: dict | None) -> dict:
    """``principal_scope`` plus ``attachment_access``: True only for a turn that names attachments and passes STRICT."""
    scope = principal_scope(current_user)
    scope["attachment_access"] = bool((context or {}).get("attachments")) and await attachments_allowed(
        chat_id, current_user, request
    )
    return scope


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


async def _stream_graph_resume(
    chat_workflow_manager,
    chat_id: str,
    decision: dict,
    request_id: str,
    attachment_access: bool = False,
):
    """Stream graph resume after command approval interrupt (#1043).

    ``attachment_access`` is THIS request's STRICT session-posture verdict (#20195): it replaces the one the
    interrupted turn checkpointed, so only an owner or admin who passes now gets file text in the resumed answer.
    """
    try:
        evt = {"type": "start", "session_id": chat_id, "request_id": request_id}
        yield f"data: {json.dumps(evt)}\n\n"

        async for msg in chat_workflow_manager.resume_graph(
            session_id=chat_id, decision=decision, attachment_access=attachment_access
        ):
            msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
            yield f"data: {json.dumps(msg_data)}\n\n"

        yield (f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n")

    except Exception as e:
        logger.error("[%s] Graph resume error: %s", request_id, e, exc_info=True)
        evt = {
            "type": "error",
            "content": "An internal error occurred",
            "request_id": request_id,
        }
        yield f"data: {json.dumps(evt)}\n\n"
