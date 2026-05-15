# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Messaging Module

Handles WebSocket communication for workflow status updates.
"""

import logging
from typing import Any, Dict

from type_defs.common import Metadata

logger = logging.getLogger(__name__)


class WorkflowMessenger:
    """Handles workflow messaging via WebSocket"""

    def __init__(self):
        """Initialize messenger with empty terminal sessions dictionary."""
        # Terminal WebSocket sessions keyed by session_id
        self.terminal_sessions: Dict[str, Any] = {}

    def register_session(self, session_id: str, websocket: Any) -> None:
        """Register a WebSocket session"""
        self.terminal_sessions[session_id] = websocket
        logger.debug("Registered WebSocket session: %s", session_id)

    def unregister_session(self, session_id: str) -> None:
        """Unregister a WebSocket session"""
        if session_id in self.terminal_sessions:
            del self.terminal_sessions[session_id]
            logger.debug("Unregistered WebSocket session: %s", session_id)

    async def send_message(self, session_id: str, message: Metadata) -> bool:
        """Send workflow control message to frontend terminal"""
        try:
            # This would integrate with the existing WebSocket system
            # For now, just log the message
            logger.info("Sending workflow message to %s: %s", session_id, message)

            # In real implementation, this would send via WebSocket to the terminal
            # websocket = self.terminal_sessions.get(session_id)
            # if websocket:
            #     await websocket.send_text(json.dumps(message))

            return True

        except Exception as e:
            logger.error("Failed to send workflow message: %s", e)
            return False
