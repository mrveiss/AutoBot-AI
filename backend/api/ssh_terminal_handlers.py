# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSH Terminal Handlers - WebSocket handler for SSH-based terminal connections.

This module provides terminal handling for user-defined infrastructure hosts
accessed via SSH. Used in the chat interface for connecting to external hosts
stored in the secrets system.

Related Issue: #715 - Dynamic SSH/VNC host management via secrets

Key Differences from ConsolidatedTerminalWebSocket:
- Uses SSH connection instead of local PTY
- Connects to user-defined infrastructure hosts
- Supports command extraction on first connect
- Integrates with infrastructure knowledge base
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import WebSocket

from backend.api.terminal_models import (
    CommandRiskLevel,
    MODERATE_RISK_PATTERNS,
    RISKY_COMMAND_PATTERNS,
    SecurityLevel,
)
from backend.services.ssh_connection_service import (
    SSHConnectionService,
    SSHSession,
    get_ssh_connection_service,
)
from backend.services.infrastructure_host_service import get_infrastructure_host_service
from src.chat_history import ChatHistoryManager
from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class SSHTerminalWebSocket:
    """
    WebSocket handler for SSH-based terminal connections to infrastructure hosts.

    This handler connects to user-defined hosts stored in the secrets system,
    providing terminal access from the chat interface.
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        host_id: str,
        conversation_id: Optional[str] = None,
        redis_client=None,
    ):
        """
        Initialize SSH terminal handler.

        Args:
            websocket: FastAPI WebSocket instance
            session_id: Unique session identifier
            host_id: Infrastructure host ID from secrets
            conversation_id: Optional chat conversation ID
            redis_client: Optional Redis client for logging
        """
        self.websocket = websocket
        self.session_id = session_id
        self.host_id = host_id
        self.conversation_id = conversation_id
        self.active = False

        # SSH connection
        self.ssh_service = get_ssh_connection_service()
        self.host_service = get_infrastructure_host_service()
        self.ssh_session: Optional[SSHSession] = None

        # Terminal state
        self.command_history = []
        self.session_start_time = datetime.now()

        # Output handling
        self._output_buffer = ""
        self._last_output_save_time = time.time()
        self._output_lock = asyncio.Lock()
        self._reader_task: Optional[asyncio.Task] = None

        # Chat integration
        if conversation_id:
            from src.logging.terminal_logger import TerminalLogger
            self.terminal_logger = TerminalLogger(
                redis_client=redis_client, data_dir="data/chats"
            )
            self.chat_history_manager = ChatHistoryManager()
        else:
            self.terminal_logger = None
            self.chat_history_manager = None

    async def start(self) -> bool:
        """
        Start the SSH terminal session.

        Returns:
            True if session started successfully, False otherwise
        """
        self.active = True

        # Get host info for display
        host = self.host_service.get_host(self.host_id)
        if not host:
            await self._send_error("Host not found")
            return False

        try:
            # Establish SSH connection with interactive PTY
            self.ssh_session = await self.ssh_service.create_interactive_session(
                host_id=self.host_id,
                term_type="xterm-256color",
                cols=80,
                rows=24,
                accessed_by=f"chat_terminal:{self.session_id}",
            )

            # Start output reader task
            self._reader_task = asyncio.create_task(self._read_ssh_output())

            # Send connection notification
            await self.send_message({
                "type": "connected",
                "content": f"Connected to {host.name} ({host.host})\r\n",
                "host": {
                    "id": host.id,
                    "name": host.name,
                    "address": host.host,
                    "os": host.os,
                },
            })

            logger.info(
                "SSH terminal session started: %s -> %s (%s)",
                self.session_id, host.name, host.host
            )

            # Trigger command extraction if not already done
            if not host.commands_extracted:
                asyncio.create_task(self._trigger_command_extraction())

            return True

        except ConnectionError as e:
            await self._send_error(f"Connection failed: {e}")
            return False
        except Exception as e:
            logger.error("Failed to start SSH terminal: %s", e)
            await self._send_error(f"Failed to connect: {e}")
            return False

    async def _trigger_command_extraction(self) -> None:
        """Trigger command extraction for knowledge base (runs in background)."""
        try:
            # Import dynamically to avoid circular imports
            from backend.services.command_extraction_service import (
                extract_host_commands,
            )
            await extract_host_commands(self.host_id)
        except ImportError:
            logger.debug("Command extraction service not yet implemented")
        except Exception as e:
            logger.warning("Command extraction failed: %s", e)

    async def _read_ssh_output(self) -> None:
        """Async task to read SSH output and send to WebSocket."""
        logger.info("Starting SSH output reader for session %s", self.session_id)

        while self.active and self.ssh_session:
            try:
                # Read from SSH channel
                data = await self.ssh_service.read_from_channel(self.ssh_session)

                if data:
                    content = data.decode("utf-8", errors="replace")
                    await self.send_output(content)
                else:
                    await asyncio.sleep(TimingConstants.POLL_INTERVAL)

                # Check if channel is closed
                if (
                    self.ssh_session.channel and
                    self.ssh_session.channel.closed
                ):
                    logger.info("SSH channel closed for session %s", self.session_id)
                    await self.send_message({
                        "type": "terminal_closed",
                        "content": "SSH session ended",
                    })
                    break

            except Exception as e:
                logger.error("Error reading SSH output: %s", e)
                break

        logger.info("SSH output reader stopped for session %s", self.session_id)

    async def cleanup(self) -> None:
        """Clean up SSH terminal resources."""
        self.active = False

        # Flush output buffer to chat
        if self.chat_history_manager and self.conversation_id:
            try:
                async with self._output_lock:
                    if self._output_buffer.strip():
                        from src.utils.encoding_utils import strip_ansi_codes
                        clean_content = strip_ansi_codes(self._output_buffer).strip()
                        if clean_content:
                            await self.chat_history_manager.add_message(
                                sender="terminal",
                                text=clean_content,
                                message_type="terminal_output",
                                session_id=self.conversation_id,
                            )
                    self._output_buffer = ""
            except Exception as e:
                logger.error("Failed to flush output buffer: %s", e)

        # Cancel reader task
        if self._reader_task:
            try:
                self._reader_task.cancel()
                await asyncio.wait_for(self._reader_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.error("Error cancelling reader task: %s", e)

        # Disconnect SSH
        if self.ssh_session:
            try:
                await self.ssh_service.disconnect(self.host_id)
            except Exception as e:
                logger.error("Error disconnecting SSH: %s", e)

        logger.info("SSH terminal session cleaned up: %s", self.session_id)

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
        })

    async def send_to_terminal(self, text: str) -> None:
        """Send text input to SSH terminal."""
        if not self.ssh_session or not self.ssh_session.is_interactive:
            await self._send_error("SSH session not available")
            return

        try:
            await self.ssh_service.write_to_channel(
                self.ssh_session,
                text.encode("utf-8"),
            )
        except Exception as e:
            logger.error("Error writing to SSH: %s", e)
            await self._send_error(f"Terminal error: {e}")

    async def send_output(self, content: str) -> None:
        """Send terminal output to client with chat integration."""
        # Send to WebSocket
        await self.send_message({
            "type": "output",
            "content": content,
            "metadata": {
                "session_id": self.session_id,
                "host_id": self.host_id,
                "timestamp": time.time(),
                "terminal_type": "ssh",
            },
        })

        # Buffer for chat integration
        if self.chat_history_manager and self.conversation_id:
            async with self._output_lock:
                self._output_buffer += content
                current_time = time.time()

                # Save periodically or on significant content
                should_save = (
                    len(self._output_buffer) > 500 or
                    (current_time - self._last_output_save_time) > 2.0 or
                    "\n" in content
                )

                if should_save and self._output_buffer.strip():
                    await self._save_buffer_to_chat()

    async def _save_buffer_to_chat(self) -> None:
        """Save buffered output to chat history."""
        from src.utils.encoding_utils import strip_ansi_codes, is_terminal_prompt

        clean_content = strip_ansi_codes(self._output_buffer).strip()

        # Skip prompts and empty content
        if not clean_content or is_terminal_prompt(clean_content):
            self._output_buffer = ""
            self._last_output_save_time = time.time()
            return

        try:
            await self.chat_history_manager.add_message(
                sender="terminal",
                text=clean_content,
                message_type="terminal_output",
                session_id=self.conversation_id,
            )
            self._output_buffer = ""
            self._last_output_save_time = time.time()
        except Exception as e:
            logger.error("Failed to save output to chat: %s", e)

    def _get_message_handlers(self) -> Dict[str, Callable]:
        """Get dispatch table for message type handlers."""
        return {
            "input": self._handle_input_message,
            "terminal_stdin": self._handle_terminal_stdin,
            "ping": self._handle_ping_message,
            "resize": self._handle_resize,
            "signal": self._handle_signal_message,
        }

    async def handle_message(self, message: dict) -> None:
        """Handle incoming WebSocket message."""
        try:
            message_type = message.get("type", "unknown")
            handlers = self._get_message_handlers()
            handler = handlers.get(message_type)

            if handler:
                await handler(message)
            else:
                logger.warning("Unknown message type: %s", message_type)

        except Exception as e:
            logger.error("Error handling message: %s", e)
            await self._send_error(f"Error processing message: {e}")

    async def _handle_ping_message(self, message: dict) -> None:
        """Handle ping message."""
        await self.send_message({"type": "pong", "timestamp": time.time()})

    async def _handle_input_message(self, message: dict) -> None:
        """Handle terminal input."""
        text = message.get("text") or message.get("content", "")
        if not text:
            return

        # Track command for history
        if "\r" in text or "\n" in text:
            if not hasattr(self, "_command_buffer"):
                self._command_buffer = ""

            command = (self._command_buffer + text).split("\r")[0].split("\n")[0].strip()
            self._command_buffer = ""

            if command:
                self.command_history.append({
                    "command": command,
                    "timestamp": datetime.now(),
                })

                # Log command to chat
                if self.chat_history_manager and self.conversation_id:
                    try:
                        await self.chat_history_manager.add_message(
                            sender="terminal",
                            text=f"$ {command}",
                            message_type="terminal_command",
                            session_id=self.conversation_id,
                        )
                    except Exception as e:
                        logger.error("Failed to save command to chat: %s", e)
        else:
            if not hasattr(self, "_command_buffer"):
                self._command_buffer = ""
            self._command_buffer += text

        await self.send_to_terminal(text)

    async def _handle_terminal_stdin(self, message: dict) -> None:
        """Handle stdin input for interactive prompts."""
        content = message.get("content", "")
        if not content:
            return

        await self.send_to_terminal(content)

    async def _handle_resize(self, message: dict) -> None:
        """Handle terminal resize requests."""
        rows = message.get("rows", 24)
        cols = message.get("cols", 80)

        if self.ssh_session and self.ssh_session.is_interactive:
            try:
                await self.ssh_service.resize_pty(self.ssh_session, cols, rows)
            except Exception as e:
                logger.error("Error resizing SSH PTY: %s", e)

    async def _handle_signal_message(self, message: dict) -> None:
        """Handle signal requests (send character sequences for SSH)."""
        signal_name = message.get("signal", "SIGINT")

        # Map signals to control sequences
        signal_sequences = {
            "SIGINT": b"\x03",   # Ctrl+C
            "SIGTERM": b"\x03",  # Treat as Ctrl+C for SSH
            "SIGKILL": b"\x03",  # Treat as Ctrl+C for SSH
            "SIGHUP": b"\x01\x04",  # Ctrl+A, Ctrl+D
        }

        seq = signal_sequences.get(signal_name, b"\x03")

        if self.ssh_session and self.ssh_session.is_interactive:
            try:
                await self.ssh_service.write_to_channel(self.ssh_session, seq)
                await self.send_message({
                    "type": "signal_sent",
                    "signal": signal_name,
                    "timestamp": time.time(),
                })
            except Exception as e:
                logger.error("Error sending signal: %s", e)
                await self._send_error(f"Error sending signal: {e}")


class SSHTerminalManager:
    """Manager for SSH terminal sessions."""

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


# Global SSH terminal manager
ssh_terminal_manager = SSHTerminalManager()
