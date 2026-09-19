# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Messaging Module

Handles WebSocket communication for workflow status updates.
"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from type_defs.common import Metadata

logger = get_logger(__name__)


class WorkflowMessenger:
    """Handles workflow messaging via WebSocket"""

    def __init__(self) -> None:
        """Initialize messenger with empty terminal sessions dictionary."""
        # Terminal WebSocket sessions keyed by session_id
        self.terminal_sessions: Dict[str, Any] = {}
        self.session_owners: Dict[str, str] = {}  # who claimed each slot (#17009)

    def register_session(self, session_id: str, websocket: Any) -> None:
        """Register a WebSocket session"""
        self.terminal_sessions[session_id] = websocket
        logger.debug("Registered WebSocket session: %s", session_id)

    def claim_session(self, session_id: str, websocket: Any, owner: str) -> bool:
        """Register *websocket* as *owner*'s socket for *session_id*, unless another user holds it (#17009).

        The slot was a plain dict write, so any caller naming a session took it over
        and received that session's workflow messages. A slot is now its claimant's:
        the same user may reconnect over it, a different user is refused.
        """
        holder = self.session_owners.get(session_id)
        if session_id in self.terminal_sessions and holder not in (None, owner):
            logger.warning("Refused %s: workflow session %s belongs to another user", owner, session_id)
            return False
        self.terminal_sessions[session_id] = websocket
        self.session_owners[session_id] = owner
        return True

    def release_session(self, session_id: str, websocket: Any) -> None:
        """Free *session_id*'s slot if *websocket* still holds it, so a stale socket never frees a newer one."""
        if self.terminal_sessions.get(session_id) is websocket:
            del self.terminal_sessions[session_id]
            self.session_owners.pop(session_id, None)

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
