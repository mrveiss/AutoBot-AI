# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSH Terminal Handlers - Stub for SLM API integration.

Issue #729: SSH operations to infrastructure hosts are now handled by slm-server.
This module provides backward-compatible stubs that redirect clients to SLM.

For infrastructure SSH terminal connections, use slm-admin or the SLM API directly:
- SLM Terminal API: /api/terminal/ssh/{host_id}
- SLM Admin UI: slm-admin → Tools → Terminal

This file is kept for backward compatibility with imports but functionality
has been moved to slm-server as part of the layer separation (#729).
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class SSHTerminalWebSocket:
    """
    Stub SSH terminal handler - redirects to SLM for infrastructure connections.

    Issue #729: SSH connections to infrastructure hosts are now managed by slm-server.
    This class provides backward-compatible interface that returns deprecation message.
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        host_id: str,
        conversation_id: Optional[str] = None,
        redis_client=None,
    ):
        """Initialize SSH terminal handler stub."""
        self.websocket = websocket
        self.session_id = session_id
        self.host_id = host_id
        self.conversation_id = conversation_id
        self.active = False
        self.command_history = []
        self.session_start_time = datetime.now()

    async def start(self) -> bool:
        """
        Start SSH terminal session - returns deprecation message.

        Issue #729: SSH connections now handled by SLM server.
        """
        self.active = False
        await self._send_error(
            "SSH terminal connections to infrastructure hosts have been moved to SLM.\n"
            "Please use slm-admin → Tools → Terminal to connect to infrastructure hosts,\n"
            "or call the SLM API directly at: /api/terminal/ssh/{host_id}\n\n"
            "This is part of the layer separation (#729) - infrastructure operations\n"
            "are now managed exclusively by slm-server."
        )
        return False

    async def cleanup(self) -> None:
        """Clean up resources."""
        self.active = False
        logger.info("SSH terminal stub session cleaned up: %s", self.session_id)

    async def send_message(self, message: dict) -> None:
        """Send message to WebSocket client."""
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error("Error sending message: %s", e)

    async def _send_error(self, content: str) -> None:
        """Send error message to client."""
        await self.send_message({
            "type": "error",
            "content": content,
            "timestamp": time.time(),
            "redirect": {
                "type": "slm",
                "message": "Use SLM for infrastructure SSH connections",
                "url": "/api/terminal/ssh/{host_id}",
            },
        })

    async def send_to_terminal(self, text: str) -> None:
        """Send text input - not supported, redirects to SLM."""
        await self._send_error("SSH terminal not available. Use SLM for infrastructure connections.")

    async def send_output(self, content: str) -> None:
        """Send terminal output - stub."""
        pass

    async def handle_message(self, message: dict) -> None:
        """Handle incoming WebSocket message - returns deprecation notice."""
        await self._send_error("SSH terminal moved to SLM server (#729)")


class SSHTerminalManager:
    """Manager for SSH terminal sessions - stub implementation."""

    def __init__(self):
        """Initialize SSH terminal manager."""
        self.active_sessions: Dict[str, SSHTerminalWebSocket] = {}
        self._lock = asyncio.Lock()

    async def add_session(self, session_id: str, terminal: SSHTerminalWebSocket) -> None:
        """Add an SSH terminal session."""
        async with self._lock:
            self.active_sessions[session_id] = terminal

    async def remove_session(self, session_id: str) -> None:
        """Remove an SSH terminal session."""
        async with self._lock:
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]

    async def get_session(self, session_id: str) -> Optional[SSHTerminalWebSocket]:
        """Get an SSH terminal session."""
        async with self._lock:
            return self.active_sessions.get(session_id)

    async def close_session(self, session_id: str) -> None:
        """Close and cleanup an SSH terminal session."""
        terminal = None
        async with self._lock:
            terminal = self.active_sessions.get(session_id)

        if terminal:
            await terminal.cleanup()
            await self.remove_session(session_id)

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """List all active SSH terminal sessions."""
        return {
            sid: {
                "host_id": terminal.host_id,
                "conversation_id": terminal.conversation_id,
                "start_time": terminal.session_start_time.isoformat(),
                "active": terminal.active,
            }
            for sid, terminal in self.active_sessions.items()
        }


# Global SSH terminal manager (stub)
ssh_terminal_manager = SSHTerminalManager()
