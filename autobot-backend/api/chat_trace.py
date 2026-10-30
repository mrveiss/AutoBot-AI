# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /chat/sessions/{session_id}/trace: a read-only trace of one chat session (#19963).

Owner or admin only (``validate_session_ownership``, STRICT posture). A caller who is not
allowed to read the session gets exactly what a caller asking for a session that does not exist
gets -- a 404 -- so the route does not confirm that an id belongs to someone else. The default
posture cannot give that: it answers a non-owner 403, and in ``log_only`` lets them through.

The turns come from :func:`chat_history.session_trace.project_session_trace`; the only thing
looked up besides the stored messages is each approval's current state.
"""

from typing import Dict, List, Mapping

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_chat_trace import SessionTraceData
from api.schemas_common import DataResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from chat_history.session_trace import (
    KIND_GATE,
    KIND_TERMINAL,
    UNKNOWN,
    ApprovalRef,
    approval_refs,
    project_session_trace,
)
from models.command_execution import CommandExecution
from security.session_ownership import validate_session_ownership
from security.session_posture import SessionPosture
from utils.chat_utils import get_chat_history_manager

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)

_NOT_FOUND = "Chat session not found"


async def _terminal_states(session_id: str, refs: List[ApprovalRef]) -> Dict[ApprovalRef, str]:
    """Latest queue state of the command each terminal ref points at, by terminal session id."""
    from services.command_execution_queue import get_command_queue

    wanted = {ident for kind, ident in refs if kind == KIND_TERMINAL}
    latest: Dict[str, CommandExecution] = {}
    for command in await get_command_queue().get_chat_commands(session_id):
        if command.terminal_session_id in wanted:
            known = latest.get(command.terminal_session_id)
            if known is None or command.requested_at >= known.requested_at:
                latest[command.terminal_session_id] = command
    return {(KIND_TERMINAL, ident): cmd.state.value for ident, cmd in latest.items()}


async def _gate_state(ident: str) -> str:
    import uuid

    from services.approval_gate_service import ApprovalGateService
    from user_management.database import get_async_session_factory

    async with get_async_session_factory()() as db:
        approval = await ApprovalGateService(db).get(uuid.UUID(ident))
    return str(approval.status) if approval is not None else UNKNOWN


async def _gate_states(refs: List[ApprovalRef]) -> Dict[ApprovalRef, str]:
    states: Dict[ApprovalRef, str] = {}
    for kind, ident in refs:
        if kind != KIND_GATE:
            continue
        try:
            states[(kind, ident)] = await _gate_state(ident)
        except Exception as exc:  # one unreadable approval reads as unknown, never fails the trace
            logger.warning("Approval %s state unreadable for trace: %s", ident[:8], exc)
    return states


async def resolve_approval_states(session_id: str, refs: List[ApprovalRef]) -> Mapping[ApprovalRef, str]:
    """Current state per approval ref; a ref whose store cannot be read is left out (reads ``unknown``)."""
    states = await _gate_states(refs)
    try:
        states.update(await _terminal_states(session_id, refs))
    except Exception as exc:
        logger.warning("Command queue unreadable for trace of session %s...: %s", session_id[:8], exc)
    return states


async def _require_readable(session_id: str, request: Request) -> None:
    """Owner or admin passes; anyone else is told the session does not exist."""
    try:
        await validate_session_ownership(session_id, request, posture=SessionPosture.STRICT)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from None


@router.get("/chat/sessions/{session_id}/trace", response_model=DataResponse[SessionTraceData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_trace",
    error_code_prefix="CHAT_TRACE",
)
async def get_session_trace(
    session_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
):
    """The turns of *session_id* in order: iterations, tool verdicts, approvals, results."""
    await _require_readable(session_id, request)
    messages = await get_chat_history_manager(request).load_session(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    states = await resolve_approval_states(session_id, approval_refs(messages))
    return DataResponse(data=SessionTraceData(session_id=session_id, turns=project_session_trace(messages, states)))
