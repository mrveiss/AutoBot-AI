# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSH terminal bridge for the unified terminal API (#729, #3383).

Extracted from ``api/terminal.py`` (#14959), the same way ``terminal_handlers``
(#210) and ``terminal_tools`` (#185) were before it: that module carries the
router and had grown past its recorded size ceiling, and this is the one part of
it that answers to a different owner.

SSH connections to infrastructure hosts belong to slm-server, not to the backend
(#729). What lives here is the backward-compatible surface that says so — a
handler that accepts the WebSocket, tells the caller where the capability moved,
and stays wired into the session manager so an open connection is still tracked
and cleaned up. The ``/ws/ssh/{host_id}`` route itself stays on the router in
``api/terminal.py`` and drives the helpers below.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import WebSocket, WebSocketDisconnect

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# SSH terminal stub classes — previously in api/ssh_terminal_handlers.py.
# Issue #729: SSH operations to infrastructure hosts are now handled by slm-server.
# Issue #3383: Inlined here to eliminate the competing module.


class SSHTerminalWebSocket:
    """
    Stub SSH terminal handler — redirects to SLM for infrastructure connections.

    Issue #729: SSH connections to infrastructure hosts are now managed by slm-server.
    This class provides a backward-compatible interface that returns a deprecation message.
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        host_id: str,
        conversation_id: str | None = None,
        redis_client=None,
    ):
        """Initialize SSH terminal handler stub."""
        self.websocket = websocket
        self.session_id = session_id
        self.host_id = host_id
        self.conversation_id = conversation_id
        self.active = False
        self.command_history: list = []
        self.session_start_time = datetime.now(tz=timezone.utc)

    async def start(self) -> bool:
        """Start SSH terminal session — returns deprecation message."""
        self.active = False
        await self._send_error(
            "SSH terminal connections to infrastructure hosts have been moved to SLM.\n"
            "Please use slm-admin \u2192 Tools \u2192 Terminal to connect to infrastructure hosts,\n"
            "or call the SLM API directly at: /api/terminal/ssh/{host_id}\n\n"
            "This is part of the layer separation (#729) — infrastructure operations\n"
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
        await self.send_message(
            {
                "type": "error",
                "content": content,
                "timestamp": time.time(),
                "redirect": {
                    "type": "slm",
                    "message": "Use SLM for infrastructure SSH connections",
                    "url": "/api/terminal/ssh/{host_id}",
                },
            }
        )

    async def send_to_terminal(self, text: str) -> None:
        """Send text input — not supported, redirects to SLM."""
        await self._send_error("SSH terminal not available. Use SLM for infrastructure connections.")

    async def send_output(self, content: str) -> None:
        """Send terminal output — stub."""

    async def handle_message(self, message: dict) -> None:
        """Handle incoming WebSocket message — returns deprecation notice."""
        await self._send_error("SSH terminal moved to SLM server (#729)")


class _SSHTerminalManager:
    """Manager for SSH terminal sessions — stub implementation."""

    def __init__(self) -> None:
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
            self.active_sessions.pop(session_id, None)

    async def get_session(self, session_id: str) -> SSHTerminalWebSocket | None:
        """Get an SSH terminal session."""
        async with self._lock:
            return self.active_sessions.get(session_id)

    async def close_session(self, session_id: str) -> None:
        """Close and clean up an SSH terminal session."""
        terminal: SSHTerminalWebSocket | None = None
        async with self._lock:
            terminal = self.active_sessions.get(session_id)
        if terminal:
            await terminal.cleanup()
            await self.remove_session(session_id)

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """List all active SSH terminal sessions."""
        return {
            sid: {
                "host_id": t.host_id,
                "conversation_id": t.conversation_id,
                "start_time": t.session_start_time.isoformat(),
                "active": t.active,
            }
            for sid, t in self.active_sessions.items()
        }


ssh_terminal_manager = _SSHTerminalManager()


# SSH Terminal WebSocket (Issue #715 - Infrastructure host connections)
# Issue #729: DEPRECATED - SSH connections to infrastructure hosts moved to slm-server
# This endpoint now returns a deprecation message and redirects to SLM


async def _init_ssh_redis_client():
    """
    Initialize Redis client for SSH terminal logging.

    Issue #620: Extracted from ssh_terminal_websocket to reduce function length.

    Returns:
        Redis client or None if unavailable
    """
    try:
        from dependencies import get_async_redis_client

        return await get_async_redis_client(database="main")
    except Exception as e:
        logger.warning("Could not get Redis client for SSH terminal logging: %s", e)
        return None


async def _setup_ssh_terminal(
    websocket: WebSocket,
    session_id: str,
    host_id: str,
    conversation_id: str,
    redis_client,
) -> "SSHTerminalWebSocket":
    """
    Create and register SSH terminal handler.

    Issue #620: Extracted from ssh_terminal_websocket to reduce function length.

    Args:
        websocket: WebSocket connection
        session_id: Unique session identifier
        host_id: Target host ID
        conversation_id: Optional conversation ID
        redis_client: Redis client for logging

    Returns:
        SSHTerminalWebSocket instance
    """
    terminal = SSHTerminalWebSocket(
        websocket=websocket,
        session_id=session_id,
        host_id=host_id,
        conversation_id=conversation_id,
        redis_client=redis_client,
    )
    await ssh_terminal_manager.add_session(session_id, terminal)
    return terminal


async def _run_ssh_message_loop(websocket: WebSocket, terminal: "SSHTerminalWebSocket", session_id: str) -> None:
    """
    Run SSH WebSocket message handling loop.

    Issue #620: Extracted from ssh_terminal_websocket to reduce function length.

    Args:
        websocket: WebSocket connection
        terminal: SSH terminal handler
        session_id: Session identifier for logging
    """
    try:
        while terminal.active:
            data = await websocket.receive_text()
            message = json.loads(data)
            await terminal.handle_message(message)
    except WebSocketDisconnect:
        logger.info("SSH WebSocket disconnected: %s", session_id)
    except Exception as e:
        logger.error("Error in SSH WebSocket handling: %s", e)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "error",
                    "content": "SSH terminal error",
                    "timestamp": time.time(),
                }
            )
        )
