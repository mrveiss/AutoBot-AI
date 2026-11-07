# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Client-callable cancel for a session's current chat turn (#17273, stop control).

POST /api/chat/sessions/{session_id}/turn/cancel

Owner-only (``validate_session_ownership``, STRICT posture). Idempotent: with no turn
running it answers ``status="no_active_turn"`` instead of failing, so a stop button pressed
just as the reply finishes is not an error. The cancel runs the same teardown a
client disconnect does (``chat_workflow.turn_control``), so it reaches the
in-flight LLM call.
"""

from typing import Dict

from fastapi import APIRouter, Depends, Request

from api.schemas_chat_turn import TurnCancelData
from api.schemas_common import DataResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from chat_workflow.turn_cancel_bus import CancelOutcome, request_cancel
from chat_workflow.turn_control import REASON_CLIENT_CANCEL, cancel_turn
from security.session_ownership import validate_session_ownership
from security.session_posture import SessionPosture

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)


def _status(outcome: CancelOutcome) -> str:
    if outcome.cancelled:
        return "cancelled"
    return "no_active_turn" if outcome.confirmed else "unconfirmed"


@router.post(
    "/chat/sessions/{session_id}/turn/cancel",
    response_model=DataResponse[TurnCancelData],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_chat_turn",
    error_code_prefix="CHAT_TURN",
)
async def cancel_chat_turn(
    session_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
):
    """Cancel the turn currently running for *session_id* (owner only, on whichever worker)."""
    # STRICT: this tears a run down and drops its checkpoint, so it never rides the default
    # posture's log_only mode, which lets a non-owner who knows the id through.
    await validate_session_ownership(session_id, request, posture=SessionPosture.STRICT)
    outcome = await request_cancel(session_id, REASON_CLIENT_CANCEL, cancel_turn)
    logger.info("Turn cancel requested: session=%s cancelled=%d", session_id, outcome.cancelled)
    return DataResponse(
        data=TurnCancelData(
            session_id=session_id,
            status=_status(outcome),
            cancelled_turns=outcome.cancelled,
        )
    )
