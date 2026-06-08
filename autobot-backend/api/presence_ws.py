# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Presence WebSocket Router

Exposes the real-time presence WebSocket endpoint for collaborative sessions.
Issue #3282: collaborative multi-user support — shared sessions and workspaces.
"""

from fastapi import APIRouter, Query, WebSocket

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from websocket.presence import presence_websocket_handler

logger = get_logger(__name__)

router = APIRouter(tags=["collaboration", "websocket"])


@router.websocket("/ws/sessions/{session_id}/presence")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="session_presence",
    error_code_prefix="PRESENCE_WS",
)
async def session_presence(
    websocket: WebSocket,
    session_id: str,
    user_id: str = Query(..., description="Authenticated user ID"),
) -> None:
    """
    WebSocket endpoint for real-time session presence.

    Clients connect here to receive join/leave events and broadcast
    messages to other participants in the same session.

    Args:
        websocket: WebSocket connection
        session_id: Session to join
        user_id: Caller's user ID (passed as query param until WS auth middleware
                 is extended to cover WebSocket handshakes for this path)
    """
    logger.info("Presence WS connect: user=%s session=%s", user_id, session_id)
    await presence_websocket_handler(websocket, session_id, user_id)
