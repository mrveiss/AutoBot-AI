# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Presence WebSocket Router

Exposes the real-time presence WebSocket endpoint for collaborative sessions.
Issue #3282: collaborative multi-user support — shared sessions and workspaces.
"""

import uuid

from fastapi import APIRouter, WebSocket
from sqlalchemy import select

from api.ws_security import enforce_ws_origin
from auth_middleware import authenticate_websocket
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from models.session_collaboration import PermissionLevel, SessionCollaboration
from user_management.database import get_async_session_factory
from websocket.presence import presence_websocket_handler

logger = get_logger(__name__)

router = APIRouter(tags=["collaboration", "websocket"])

# WS close codes this router uses beyond the standard range (RFC 6455 leaves
# 4000-4999 for private use). 4001 mirrors api/live_events.py's own choice for
# "authenticated identity missing/invalid" so both live-connection endpoints
# agree on what that code means; 1008 is the standard "Policy Violation" code
# (already used by enforce_ws_origin for a cross-origin refusal), reused here
# for "identity verified, but not a participant of this session".
_WS_CLOSE_UNAUTHENTICATED = 4001
_WS_CLOSE_POLICY_VIOLATION = 1008


async def _authorized_participant(session_id: str, user_id: uuid.UUID) -> bool:
    """Is *user_id* the owner or a collaborator (any permission level) of *session_id*?

    Owns its own DB session -- a single seam a test can patch wholesale
    without also needing a real database connection to exercise the
    surrounding auth flow.
    """
    session_factory = get_async_session_factory()
    async with session_factory() as db:
        stmt = select(SessionCollaboration).where(SessionCollaboration.session_id == session_id)
        result = await db.execute(stmt)
        collab = result.scalar_one_or_none()
    if collab is None:
        return False
    return collab.has_permission(user_id, PermissionLevel.VIEWER)


@router.websocket("/ws/sessions/{session_id}/presence")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="session_presence",
    error_code_prefix="PRESENCE_WS",
)
async def session_presence(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    WebSocket endpoint for real-time session presence.

    Clients connect here to receive join/leave events and broadcast
    messages to other participants in the same session.

    Args:
        websocket: WebSocket connection
        session_id: Session to join
    """
    if not await enforce_ws_origin(websocket):
        return

    # #16455: the caller's identity comes ONLY from a verified JWT, never
    # from client-supplied input -- a prior version trusted a bare `user_id`
    # query param, letting any caller join any session as anyone.
    user_payload = await authenticate_websocket(websocket)
    if user_payload is None or user_payload.get("user_id") is None:
        # accept() before close(4001), matching api/live_events.py's own rule:
        # clients see a clean close frame, not a raw handshake rejection.
        await websocket.accept()
        await websocket.close(code=_WS_CLOSE_UNAUTHENTICATED, reason="Unauthorized")
        logger.info("Presence WS rejected: invalid or missing token, session=%s", session_id)
        return

    try:
        user_id = uuid.UUID(str(user_payload["user_id"]))
    except ValueError:
        await websocket.accept()
        await websocket.close(code=_WS_CLOSE_UNAUTHENTICATED, reason="Unauthorized")
        logger.warning("Presence WS rejected: malformed user_id in token, session=%s", session_id)
        return

    # Authenticated is not authorized: a verified user still must not join a
    # session they aren't a participant of.
    if not await _authorized_participant(session_id, user_id):
        await websocket.accept()
        await websocket.close(code=_WS_CLOSE_POLICY_VIOLATION, reason="Not a session participant")
        logger.info("Presence WS refused: user=%s not a participant of session=%s", user_id, session_id)
        return

    logger.info("Presence WS connect: user=%s session=%s", user_id, session_id)
    await presence_websocket_handler(websocket, session_id, str(user_id))
