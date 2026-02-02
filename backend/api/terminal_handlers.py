# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Handlers - WebSocket and Session Management Classes.

This module contains the core handler classes for terminal operations.
Extracted from terminal.py for better maintainability (Issue #185, #210).
Further modularized with Issue #290 (God class refactoring).

Classes:
- ConsolidatedTerminalWebSocket: WebSocket handler for real-time terminal I/O
- ConsolidatedTerminalManager: Session registry and lifecycle management

Supporting modules (backend/services/terminal_websocket/):
- security.py: Command risk assessment
- audit.py: Audit logging
- chat_integration.py: Chat history integration

Related Issues: #185 (Split), #210 (Terminal split), #290 (God class refactoring)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Awaitable, Callable, Dict, Optional

from fastapi import WebSocket

# Import models from dedicated module (Issue #185)
from backend.api.terminal_models import (
    MODERATE_RISK_PATTERNS,
    RISKY_COMMAND_PATTERNS,
    CommandRiskLevel,
    SecurityLevel,
)
from backend.services.simple_pty import simple_pty_manager

# Import extracted modules (Issue #290)
from backend.services.terminal_websocket import (
    HIGH_RISK_COMMAND_LEVELS,
    LOGGING_SECURITY_LEVELS,
    SHELL_OPERATORS,
)
from src.chat_history import ChatHistoryManager
from src.constants.path_constants import PATH
from src.constants.threshold_constants import TimingConstants

# Issue #380: Module-level frozenset for terminal close event types
_TERMINAL_CLOSE_EVENTS = frozenset({"eo", "close"})

# Issue #665: Module-level signal mapping for _handle_signal_message
import signal as _signal_module

_SIGNAL_MAP = {
    "SIGINT": _signal_module.SIGINT,
    "SIGTERM": _signal_module.SIGTERM,
    "SIGKILL": _signal_module.SIGKILL,
    "SIGHUP": _signal_module.SIGHUP,
}

logger = logging.getLogger(__name__)


async def _flush_cleanup_buffer(
    chat_history_manager,
    conversation_id: str,
    output_buffer: str,
) -> None:
    """Flush remaining output buffer on cleanup (Issue #315: extracted).

    Strips ANSI codes and saves clean content to chat history.
    """
    from src.utils.encoding_utils import strip_ansi_codes

    if not output_buffer.strip():
        return

    clean_content = strip_ansi_codes(output_buffer).strip()
    logger.info(
        f"[CHAT INTEGRATION] Flushing remaining output buffer on cleanup: "
        f"{len(output_buffer)} chars (clean: {len(clean_content)} chars)"
    )
    if not clean_content:
        return

    await chat_history_manager.add_message(
        sender="terminal",
        text=clean_content,
        message_type="terminal_output",
        session_id=conversation_id,
    )
    logger.info("[CHAT INTEGRATION] Buffer flushed successfully")


async def _save_buffered_output_to_chat(
    chat_history_manager,
    conversation_id: str,
    output_buffer: str,
) -> tuple:
    """Save buffered terminal output to chat if conditions met (Issue #315: extracted).

    Returns:
        Tuple of (should_reset_buffer, skip_reason or None)
    """
    from src.utils.encoding_utils import is_terminal_prompt, strip_ansi_codes

    clean_content = strip_ansi_codes(output_buffer).strip()
    is_prompt = is_terminal_prompt(clean_content)

    # Check if content should be skipped
    if not clean_content or is_prompt:
        skip_reason = "terminal prompt" if is_prompt else "only ANSI codes"
        logger.debug(
            f"[CHAT INTEGRATION] Skipping save - buffer is {skip_reason} "
            f"({len(output_buffer)} chars, clean: '{clean_content[:100]}')"
        )
        return True, skip_reason

    # Save the clean content
    try:
        logger.info(
            f"[CHAT INTEGRATION] Saving output to chat: "
            f"{len(output_buffer)} chars (clean: {len(clean_content)} chars)"
        )
        await chat_history_manager.add_message(
            sender="terminal",
            text=clean_content,
            message_type="terminal_output",
            session_id=conversation_id,
        )
        logger.info("[CHAT INTEGRATION] Output saved successfully")
        return True, None
    except Exception as e:
        logger.error("Failed to save output to chat: %s", e)
        return False, None


class ConsolidatedTerminalWebSocket:
    """
    Enhanced terminal WebSocket handler that combines features
    from all implementations
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        security_level: SecurityLevel = SecurityLevel.STANDARD,
        conversation_id: Optional[str] = None,
        redis_client=None,
    ):
        """Initialize terminal handler with WebSocket and session config."""
        self.websocket = websocket
        self.session_id = session_id
        self.conversation_id = conversation_id  # Link to chat session
        self.security_level = security_level
        self.enable_logging = security_level in LOGGING_SECURITY_LEVELS
        self.enable_workflow_control = True
        self.command_history = []
        self.audit_log = []
        self.user_role = "user"  # Could be enhanced with actual auth
        self.session_start_time = datetime.now()
        self.pty_process = None
        self.active = False
        self.terminal_adapter = None

        # CRITICAL FIX: Output buffer for chat integration
        self._output_buffer = ""
        self._last_output_save_time = time.time()
        self._output_lock = asyncio.Lock()  # Protect concurrent buffer access

        # Phase 3: Queue-based output delivery for better responsiveness
        import queue

        self.output_queue = queue.Queue(maxsize=1000)  # Limit queue size
        self._output_sender_task = None  # Will be created in start()

        # Initialize TerminalLogger for persistent command logging
        if conversation_id:
            from src.logging.terminal_logger import TerminalLogger

            self.terminal_logger = TerminalLogger(
                redis_client=redis_client, data_dir="data/chats"
            )
            # CRITICAL FIX: Initialize ChatHistoryManager for chat integration
            self.chat_history_manager = ChatHistoryManager()
        else:
            self.terminal_logger = None
            self.chat_history_manager = None

        # Initialize PTY process if security level allows
        if security_level != SecurityLevel.RESTRICTED:
            self._init_pty_process()

    def _init_pty_process(self):
        """Initialize PTY process using SimplePTY"""
        try:
            from backend.services.simple_pty import simple_pty_manager

            # Create PTY session with SimplePTY manager
            self.pty_process = simple_pty_manager.create_session(
                self.session_id, initial_cwd=str(PATH.PROJECT_ROOT)
            )

            if self.pty_process:
                logger.info(
                    f"PTY initialized successfully for session {self.session_id}"
                )
                # Output reader will be started when WebSocket is ready
                self.pty_output_task = None
            else:
                logger.error("Failed to create PTY session %s", self.session_id)
                self.pty_process = None

        except Exception as e:
            logger.error("Could not initialize PTY process: %s", e)
            self.pty_process = None

    async def _process_pty_event(self, event_type: str, content: str) -> bool:
        """
        Process PTY event (Issue #315 - extracted helper).

        Args:
            event_type: Type of event (output, eo, close)
            content: Event content

        Returns:
            True if processing should continue, False if PTY is closing
        """
        if event_type == "output":
            # Send output to WebSocket
            await self.send_output(content)
            return True

        if event_type in _TERMINAL_CLOSE_EVENTS:
            # PTY closed
            logger.info("PTY closed for session %s", self.session_id)
            await self.send_message(
                {
                    "type": "terminal_closed",
                    "content": "Terminal session ended",
                }
            )
            return False

        # Unknown event type, continue processing
        return True

    async def _read_pty_output(self):
        """
        Async task to read PTY output and send to WebSocket.

        (Issue #315 - refactored to reduce nesting depth)
        """
        logger.info("Starting PTY output reader for session %s", self.session_id)

        while self.active and self.pty_process:
            try:
                # Get output from PTY (non-blocking)
                output = self.pty_process.get_output()

                if not output:
                    # No output available, small delay to prevent CPU spinning
                    await asyncio.sleep(TimingConstants.POLL_INTERVAL)
                    continue

                # Process event using extracted helper
                event_type, content = output
                should_continue = await self._process_pty_event(event_type, content)
                if not should_continue:
                    break

            except Exception as e:
                logger.error("Error reading PTY output: %s", e)
                break

        logger.info("PTY output reader stopped for session %s", self.session_id)

    async def send_message(self, message: dict):
        """Send message to WebSocket client"""
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error("Error sending message: %s", e)

    async def send_to_terminal(self, text: str):
        """Send text input to terminal process"""
        if self.pty_process and self.pty_process.is_alive():
            # Send to actual PTY process
            try:
                success = self.pty_process.write_input(text)
                if not success:
                    await self.send_message(
                        {"type": "error", "content": "Failed to write to terminal"}
                    )
                return
            except Exception as e:
                logger.error("Error writing to PTY: %s", e)
                await self.send_message(
                    {"type": "error", "content": f"Terminal error: {str(e)}"}
                )
        else:
            # PTY not available
            await self.send_message(
                {"type": "error", "content": "Terminal not available"}
            )

    async def start(self):
        """Start the terminal session"""
        self.active = True

        # Phase 3: Start async output sender task for queue-based delivery
        self._output_sender_task = asyncio.create_task(self._async_output_sender())
        logger.info("Async output sender started for session %s", self.session_id)

        # Start PTY output reader task if PTY is available
        if self.pty_process and self.pty_process.is_alive():
            self.pty_output_task = asyncio.create_task(self._read_pty_output())
            logger.info("PTY output reader started for session %s", self.session_id)

            # NOTE: Keep PTY echo ON by default for automated/agent mode visibility
            # Frontend handles local echo for manual mode to reduce lag
            # This ensures agent commands are visible to user in automated mode
            logger.info(
                f"PTY echo enabled for session {self.session_id} (agent commands visible)"
            )

            # Send initial shell prompt/output with newline for proper formatting
            await self.send_message(
                {
                    "type": "connected",
                    "content": f"Connected to terminal session {self.session_id}\r\n",
                }
            )
        else:
            logger.warning("PTY not available for session %s", self.session_id)
            await self.send_message(
                {"type": "error", "content": "Terminal initialization failed"}
            )

    async def cleanup(self):
        """Clean up terminal resources"""
        self.active = False

        # CRITICAL FIX: Flush any remaining buffered output to chat before cleanup
        # Use lock to prevent race condition with concurrent buffer access
        if self.chat_history_manager and self.conversation_id:
            try:
                async with self._output_lock:
                    await _flush_cleanup_buffer(
                        self.chat_history_manager,
                        self.conversation_id,
                        self._output_buffer,
                    )
                    self._output_buffer = ""
            except Exception as e:
                logger.error("Failed to flush output buffer: %s", e)

        # Phase 3: Signal async output sender to stop
        if hasattr(self, "output_queue"):
            try:
                import queue

                self.output_queue.put_nowait({"type": "stop"})
            except queue.Full:
                logger.debug(
                    "Output queue full during shutdown, sender will stop via active flag"
                )
            except Exception as e:
                logger.error("Error signaling output sender to stop: %s", e)

        # Cancel output reader task if running
        if hasattr(self, "pty_output_task") and self.pty_output_task:
            try:
                self.pty_output_task.cancel()
                await asyncio.wait_for(self.pty_output_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.debug("Output task cancelled during normal shutdown")
            except Exception as e:
                logger.error("Error cancelling output task: %s", e)

        # Cancel async output sender task if running
        if hasattr(self, "_output_sender_task") and self._output_sender_task:
            try:
                self._output_sender_task.cancel()
                await asyncio.wait_for(self._output_sender_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.debug("Output sender task cancelled during normal shutdown")
            except Exception as e:
                logger.error("Error cancelling output sender task: %s", e)

        # Close PTY session using manager
        if self.pty_process:
            try:
                from backend.services.simple_pty import simple_pty_manager

                simple_pty_manager.close_session(self.session_id)
                self.pty_process = None
                logger.info("PTY session %s closed", self.session_id)
            except Exception as e:
                logger.error("Error closing PTY session: %s", e)

    def _get_message_handlers(self) -> Dict[str, Callable[[dict], Awaitable[None]]]:
        """Get dispatch table for message type handlers (Issue #336 - extracted helper)."""
        return {
            "input": self._handle_input_message,
            "terminal_stdin": self._handle_terminal_stdin,  # Issue #33
            "workflow_control": self._handle_workflow_control,
            "ping": self._handle_ping_message,
            "resize": self._handle_resize,
            "signal": self._handle_signal_message,
            "tab_completion": self._handle_tab_completion,  # Issue #756
        }

    async def _handle_ping_message(self, message: dict) -> None:
        """Handle ping message (Issue #336 - extracted handler)."""
        await self.send_message({"type": "pong", "timestamp": time.time()})

    async def _handle_tab_completion(self, message: dict) -> None:
        """
        Handle tab completion request (Issue #756 - Quick Win #5).

        Provides simple directory listing completion for terminal commands.
        The frontend sends partial input and cursor position, and this handler
        returns matching file/directory completions.

        Message format:
            {
                "type": "tab_completion",
                "text": "ls /home/user/Doc",  # Current input text
                "cursor": 18,  # Cursor position
            }

        Response format:
            {
                "type": "tab_completion",
                "completions": ["Documents/", "Downloads/"],
                "prefix": "/home/user/Doc",
            }
        """
        try:
            text = message.get("text", "")
            cursor_pos = message.get("cursor", len(text))

            # Extract the word at cursor position for completion
            prefix = self._extract_completion_prefix(text, cursor_pos)

            # Get completions for the prefix
            completions = await self._get_path_completions(prefix)

            await self.send_message(
                {
                    "type": "tab_completion",
                    "completions": completions,
                    "prefix": prefix,
                }
            )

        except Exception as e:
            logger.warning("Tab completion error: %s", e)
            await self.send_message(
                {
                    "type": "tab_completion",
                    "completions": [],
                    "prefix": "",
                    "error": str(e),
                }
            )

    def _extract_completion_prefix(self, text: str, cursor_pos: int) -> str:
        """
        Extract the word/path at cursor position for completion.

        Issue #756: Helper for tab completion.
        """
        if not text:
            return ""

        # Get text up to cursor
        text_to_cursor = text[:cursor_pos]

        # Find the start of the current word (space-delimited)
        # Look for the last space before cursor
        last_space = text_to_cursor.rfind(" ")
        if last_space == -1:
            prefix = text_to_cursor
        else:
            prefix = text_to_cursor[last_space + 1 :]

        # Expand home directory
        if prefix.startswith("~"):
            prefix = os.path.expanduser(prefix)

        return prefix

    async def _get_path_completions(self, prefix: str, max_results: int = 20) -> list:
        """
        Get file/directory completions for a path prefix.

        Issue #756: Simple directory listing for tab completion.

        Args:
            prefix: Path prefix to complete
            max_results: Maximum number of completions to return

        Returns:
            List of matching paths with directory indicator (/)
        """

        if not prefix:
            return []

        try:
            # Normalize path
            if prefix.startswith("~"):
                prefix = os.path.expanduser(prefix)

            # Get directory and partial name
            if os.path.isdir(prefix):
                directory = prefix
                partial = ""
            else:
                directory = os.path.dirname(prefix) or "."
                partial = os.path.basename(prefix)

            # Check directory exists
            if not os.path.isdir(directory):
                return []

            # List directory contents
            try:
                entries = os.listdir(directory)
            except PermissionError:
                return []

            # Filter by prefix
            matching = []
            for entry in entries:
                if partial and not entry.lower().startswith(partial.lower()):
                    continue

                full_path = os.path.join(directory, entry)
                if os.path.isdir(full_path):
                    matching.append(entry + "/")
                else:
                    matching.append(entry)

                if len(matching) >= max_results:
                    break

            return sorted(matching)

        except Exception as e:
            logger.debug("Path completion error for '%s': %s", prefix, e)
            return []

    async def handle_message(self, message: dict):
        """Enhanced message handling with security and workflow features"""
        try:
            message_type = message.get("type", "unknown")
            logger.info(
                f"[HANDLE MSG] Session {self.session_id}, Type: {message_type}, Message: {str(message)[:100]}"
            )

            # Log all messages for security tracking
            if self.enable_logging:
                self._log_command_activity(
                    "message_received",
                    {
                        "type": message_type,
                        "timestamp": datetime.now().isoformat(),
                        "session_id": self.session_id,
                    },
                )

            # Issue #336: Dispatch table lookup replaces elif chain
            handlers = self._get_message_handlers()
            handler = handlers.get(message_type)
            if handler:
                await handler(message)
            else:
                logger.warning("Unknown message type: %s", message_type)

        except Exception as e:
            logger.error("Error handling message: %s", e)
            await self.send_message(
                {
                    "type": "error",
                    "content": f"Error processing message: {str(e)}",
                    "timestamp": time.time(),
                }
            )

    # =========================================================================
    # Helper Methods for _handle_input_message (Issue #281)
    # =========================================================================

    async def _write_to_transcript(self, text: str) -> None:
        """Write input to transcript file (Issue #281: extracted)."""
        if not (self.terminal_logger and self.conversation_id):
            return

        try:
            from pathlib import Path

            import aiofiles

            from src.utils.encoding_utils import strip_ansi_codes

            # Strip ANSI escape codes before writing to transcript
            clean_text = strip_ansi_codes(text)
            if not clean_text:
                return

            transcript_file = f"{self.conversation_id}_terminal_transcript.txt"
            transcript_path = Path("data/chats") / transcript_file
            async with aiofiles.open(transcript_path, "a", encoding="utf-8") as f:
                await f.write(clean_text)
        except OSError as e:
            logger.error("Failed to write input to transcript (I/O error): %s", e)
        except Exception as e:
            logger.error("Failed to write input to transcript: %s", e)

    async def _log_command_to_terminal_logger(self, command: str, status: str) -> None:
        """Log command to TerminalLogger (Issue #281: extracted)."""
        if not (self.terminal_logger and self.conversation_id):
            logger.warning(
                f"[MANUAL CMD] Skipping log - terminal_logger={self.terminal_logger is not None}, "
                f"conversation_id={self.conversation_id}"
            )
            return

        try:
            logger.info(
                f"[MANUAL CMD] Logging to {self.conversation_id}: {command[:50]}"
            )
            await self.terminal_logger.log_command(
                session_id=self.conversation_id,
                command=command,
                run_type="manual",
                status=status,
                user_id=None,
            )
            logger.info("[MANUAL CMD] Successfully logged to %s", self.conversation_id)
        except Exception as e:
            logger.error("Failed to log command to TerminalLogger: %s", e)

    async def _save_command_to_chat(self, command: str) -> None:
        """Save command as terminal message to chat (Issue #281: extracted)."""
        if not (self.chat_history_manager and self.conversation_id):
            return

        try:
            logger.info("[CHAT INTEGRATION] Saving command to chat: %s", command[:50])
            await self.chat_history_manager.add_message(
                sender="terminal",
                text=f"$ {command}",
                message_type="terminal_command",
                session_id=self.conversation_id,
            )
            logger.info("[CHAT INTEGRATION] Command saved successfully")
        except Exception as e:
            logger.error("Failed to save command to chat: %s", e)

    async def _handle_complete_command(self, command: str, text: str) -> bool:
        """Handle a complete command with security assessment (Issue #281: extracted).

        Returns True if command was blocked, False otherwise.
        """
        # Security assessment
        risk_level = self._assess_command_risk(command)

        # Log command for audit trail
        if self.enable_logging:
            self._log_command_activity(
                "command_input",
                {
                    "command": command,
                    "risk_level": risk_level.value,
                    "user_role": self.user_role,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Log to TerminalLogger for persistent storage
        logger.info(
            f"[MANUAL CMD DEBUG] terminal_logger={self.terminal_logger is not None}, "
            f"conversation_id={self.conversation_id}, command={command[:50]}"
        )
        await self._log_command_to_terminal_logger(command, "executing")

        # Save command to chat
        await self._save_command_to_chat(command)

        # Add to command history
        self.command_history.append(
            {
                "command": command,
                "timestamp": datetime.now(),
                "risk_level": risk_level.value,
            }
        )

        # Apply security restrictions
        if await self._should_block_command(command, risk_level):
            await self.send_message(
                {
                    "type": "security_warning",
                    "content": (
                        f"Command blocked due to {risk_level.value} "
                        f"risk level: {command}"
                    ),
                    "risk_level": risk_level.value,
                    "timestamp": time.time(),
                }
            )
            return True  # Command was blocked

        # Send to terminal
        await self.send_to_terminal(text)

        # Log command completion
        await self._log_command_to_terminal_logger(command, "sent")

        return False  # Command was not blocked

    async def _handle_input_message(self, message: dict):
        """
        Handle terminal input with security assessment.

        Issue #281: Refactored from 169 lines to use extracted helper methods.
        """
        logger.info(
            f"[_handle_input_message] CALLED for session {self.session_id}, message: {str(message)[:100]}"
        )

        # Support both 'text' and 'content' fields for compatibility
        text = message.get("text") or message.get("content", "")
        logger.info(
            f"[_handle_input_message] Extracted text: {repr(text[:50]) if text else 'EMPTY'}"
        )

        if not text:
            logger.warning(
                "[_handle_input_message] No text found in message, returning"
            )
            return

        # Check if command is complete (Enter pressed)
        is_command_complete = "\r" in text or "\n" in text

        # Build command buffer for this session
        if not hasattr(self, "_command_buffer"):
            self._command_buffer = ""

        # Log ALL input to transcript (Issue #281: uses helper)
        await self._write_to_transcript(text)

        if is_command_complete:
            # Extract command before the newline
            command = (
                (self._command_buffer + text).split("\r")[0].split("\n")[0].strip()
            )
            self._command_buffer = ""  # Reset buffer

            # Only process non-empty commands
            if not command:
                await self.send_to_terminal(text)
                return

            logger.info(
                f"[COMPLETE COMMAND] Session {self.session_id}: {repr(command)}"
            )

            # Handle complete command with security (Issue #281: uses helper)
            await self._handle_complete_command(command, text)
        else:
            # Accumulate characters until Enter is pressed
            self._command_buffer += text
            await self.send_to_terminal(text)

    async def _validate_stdin_size(self, content: str) -> bool:
        """
        Validate stdin content size (Issue #315 - extracted helper).

        Args:
            content: Content to validate

        Returns:
            True if valid, False if oversized
        """
        MAX_STDIN_SIZE = 4096  # 4KB max per stdin message
        if len(content) > MAX_STDIN_SIZE:
            logger.warning(
                f"[STDIN] Rejected oversized input: {len(content)} bytes (max: {MAX_STDIN_SIZE})"
            )
            await self.send_message(
                {
                    "type": "error",
                    "content": f"Input too large (max {MAX_STDIN_SIZE} bytes)",
                    "timestamp": time.time(),
                }
            )
            return False
        return True

    async def _validate_pty_available(self) -> bool:
        """
        Validate PTY process is available (Issue #315 - extracted helper).

        Returns:
            True if PTY available, False otherwise
        """
        if not self.pty_process:
            logger.error("[STDIN] No PTY process for session %s", self.session_id)
            await self.send_message(
                {
                    "type": "error",
                    "content": "No terminal session available",
                    "timestamp": time.time(),
                }
            )
            return False
        return True

    async def _write_stdin_to_pty(
        self, content: str, is_password: bool, command_id: Optional[str]
    ) -> bool:
        """
        Write stdin to PTY with password echo handling (Issue #315 - extracted helper).

        Args:
            content: Content to write
            is_password: Whether this is password input
            command_id: Optional command ID

        Returns:
            True if successful, False otherwise
        """
        success = self.pty_process.write_input(content)

        if not success:
            logger.error(
                f"[STDIN] Failed to write to PTY for session {self.session_id}"
            )
            await self.send_message(
                {
                    "type": "error",
                    "content": "Failed to send input to terminal",
                    "timestamp": time.time(),
                }
            )
            return False

        logger.info(
            f"[STDIN] Successfully sent {len(content)} bytes to PTY "
            f"(password: {is_password}, command_id: {command_id})"
        )

        # Re-enable echo after password (if it was disabled)
        if is_password:
            # Brief delay for password processing before re-enabling echo
            await asyncio.sleep(TimingConstants.MICRO_DELAY)
            self.pty_process.set_echo(True)
            logger.info("[STDIN] Re-enabled echo after password input")

        return True

    async def _handle_stdin_error(self, error: Exception, is_password: bool) -> None:
        """Handle stdin write error with echo recovery (Issue #315: extracted).

        Args:
            error: The exception that occurred
            is_password: Whether password mode was active (echo disabled)
        """
        logger.error("[STDIN] Error writing to PTY: %s", error)

        # Re-enable echo if it was disabled (ensure terminal doesn't stay in silent mode)
        if is_password:
            try:
                self.pty_process.set_echo(True)
            except Exception as echo_err:
                logger.debug("Failed to re-enable echo: %s", echo_err)

        await self.send_message(
            {
                "type": "error",
                "content": f"Error sending input: {str(error)}",
                "timestamp": time.time(),
            }
        )

    async def _handle_terminal_stdin(self, message: dict):
        """
        Handle stdin input for interactive commands (Issue #33)

        This is separate from _handle_input_message() which builds command buffers.
        This handler sends input DIRECTLY to the PTY for interactive prompts
        (password prompts, SSH confirmations, interactive Python input(), etc.)

        Security controls:
        - Size limit: 4KB max per message
        - Session validation
        - No command logging (passwords must never be logged)
        - Disabled echo for password-type inputs

        Message format:
        {
            "type": "terminal_stdin",
            "content": "user input text\\n",
            "is_password": false,  # Optional: disable echo for password input
            "command_id": "cmd-uuid"  # Optional: link to command approval
        }

        (Issue #315 - refactored to reduce nesting depth)
        """
        logger.info(
            f"[STDIN] Session {self.session_id}, receiving stdin for interactive command"
        )

        # Extract stdin content
        content = message.get("content", "")
        is_password = message.get("is_password", False)
        command_id = message.get("command_id")  # For linking to approved command

        # Validate input size (early return)
        if not await self._validate_stdin_size(content):
            return

        # Validate PTY exists (early return)
        if not await self._validate_pty_available():
            return

        # Disable echo for password input (Issue #33 Phase 4)
        if is_password:
            logger.info(
                f"[STDIN] Disabling echo for password input (command_id: {command_id})"
            )
            self.pty_process.set_echo(False)

        try:
            # Write stdin to PTY using extracted helper
            await self._write_stdin_to_pty(content, is_password, command_id)
        except Exception as e:
            # Use extracted error handler (Issue #315)
            await self._handle_stdin_error(e, is_password)

    async def _handle_workflow_control(self, message: dict):
        """Handle workflow automation control messages"""
        if not self.enable_workflow_control:
            return

        action = message.get("action")
        workflow_id = message.get("workflow_id")

        # Log workflow control action
        if self.enable_logging:
            self._log_command_activity(
                "workflow_control",
                {
                    "action": action,
                    "workflow_id": workflow_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Send confirmation
        await self.send_message(
            {
                "type": "workflow_control_ack",
                "action": action,
                "workflow_id": workflow_id,
                "status": "received",
                "timestamp": time.time(),
            }
        )

    async def _handle_resize(self, message: dict):
        """Handle terminal resize requests"""
        rows = message.get("rows", 24)
        cols = message.get("cols", 80)

        try:
            if self.pty_process and self.pty_process.isalive():
                self.pty_process.setwinsize(rows, cols)

            if self.enable_logging:
                self._log_command_activity(
                    "terminal_resize",
                    {
                        "rows": rows,
                        "cols": cols,
                        "timestamp": datetime.now().isoformat(),
                    },
                )

        except Exception as e:
            logger.error("Error resizing terminal: %s", e)

    async def _send_signal_error(self, message: str) -> None:
        """Send signal error message to client (Issue #665: extracted helper)."""
        await self.send_message(
            {
                "type": "error",
                "content": message,
                "timestamp": time.time(),
            }
        )

    async def _send_signal_to_pty(self, signal_name: str, sig: int) -> bool:
        """
        Send signal to PTY process and notify client (Issue #665: extracted helper).

        Returns True if signal was sent successfully.
        """
        if not self.pty_process:
            logger.warning("No PTY process to send signal to")
            await self._send_signal_error("No active process to interrupt")
            return False

        success = self.pty_process.send_signal(sig)
        if success:
            logger.info("Sent %s to PTY process", signal_name)
            await self.send_message(
                {
                    "type": "signal_sent",
                    "signal": signal_name,
                    "timestamp": time.time(),
                }
            )
        else:
            logger.error("Failed to send %s", signal_name)
            await self._send_signal_error(f"Failed to send signal: {signal_name}")

        return success

    async def _handle_signal_message(self, message: dict):
        """
        Handle signal requests (SIGINT, SIGTERM, etc.).

        Issue #665: Refactored to use module-level _SIGNAL_MAP and helper methods.
        """
        signal_name = message.get("signal", "SIGINT")

        try:
            sig = _SIGNAL_MAP.get(signal_name)
            if not sig:
                logger.warning("Unknown signal: %s", signal_name)
                await self._send_signal_error(f"Unknown signal: {signal_name}")
                return

            success = await self._send_signal_to_pty(signal_name, sig)

            if self.enable_logging:
                self._log_command_activity(
                    "signal_sent",
                    {
                        "signal": signal_name,
                        "timestamp": datetime.now().isoformat(),
                        "success": success,
                    },
                )

        except Exception as e:
            logger.error("Error sending signal: %s", e)
            await self._send_signal_error(f"Error sending signal: {str(e)}")

    def _assess_command_risk(self, command: str) -> CommandRiskLevel:
        """Assess the security risk level of a command"""
        command_lower = command.lower().strip()

        # Check for dangerous patterns
        for pattern in RISKY_COMMAND_PATTERNS:
            if pattern in command_lower:
                return CommandRiskLevel.DANGEROUS

        # Check for moderate risk patterns
        for pattern in MODERATE_RISK_PATTERNS:
            if pattern in command_lower:
                return CommandRiskLevel.MODERATE

        # Special checks for high-risk operations (Issue #326: O(1) lookups)
        if any(x in command_lower for x in SHELL_OPERATORS):
            return CommandRiskLevel.HIGH

        return CommandRiskLevel.SAFE

    async def _should_block_command(
        self, command: str, risk_level: CommandRiskLevel
    ) -> bool:
        """Determine if command should be blocked based on security level"""
        if self.security_level == SecurityLevel.RESTRICTED:
            return risk_level in HIGH_RISK_COMMAND_LEVELS
        elif self.security_level == SecurityLevel.ELEVATED:
            return risk_level == CommandRiskLevel.DANGEROUS

        return False  # STANDARD level allows most commands

    def _log_command_activity(self, activity_type: str, data: dict):
        """Log command activity for security audit trail"""
        log_entry = {
            "activity_type": activity_type,
            "session_id": self.session_id,
            "user_role": self.user_role,
            "security_level": self.security_level.value,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

        self.audit_log.append(log_entry)
        logger.info("Terminal audit: %s", json.dumps(log_entry))

    def _build_output_message(self, content: str) -> dict:
        """Build standardized output message format (Issue #486: extracted)."""
        return {
            "type": "output",
            "content": content,
            "metadata": {
                "session_id": self.session_id,
                "timestamp": time.time(),
                "terminal_type": "consolidated",
                "security_level": self.security_level.value,
            },
        }

    async def _queue_output_message(self, message: dict) -> bool:
        """Queue message for async delivery (Issue #486: extracted)."""
        import queue

        try:
            self.output_queue.put_nowait(message)
            return True
        except queue.Full:
            try:
                self.output_queue.get_nowait()
                self.output_queue.put_nowait(message)
                logger.warning(
                    "Output queue full for session %s, dropped oldest", self.session_id
                )
                return True
            except (queue.Empty, queue.Full):
                logger.error("Failed to queue output for session %s", self.session_id)
                return False
        except Exception as e:
            logger.error("Error queuing output: %s", e)
            await self.send_message(message)
            return True

    async def _log_to_transcript(self, content: str) -> None:
        """Log output to transcript file (Issue #486: extracted)."""
        if not (self.terminal_logger and self.conversation_id and content):
            return

        from pathlib import Path

        import aiofiles

        from src.utils.encoding_utils import strip_ansi_codes

        try:
            # Strip ANSI escape codes before writing to transcript
            clean_content = strip_ansi_codes(content)
            if not clean_content:
                return

            transcript_path = (
                Path("data/chats") / f"{self.conversation_id}_terminal_transcript.txt"
            )
            async with aiofiles.open(transcript_path, "a", encoding="utf-8") as f:
                await f.write(clean_content)
        except OSError as e:
            logger.error("Failed to write terminal transcript (I/O error): %s", e)
        except Exception as e:
            logger.error("Failed to write terminal transcript: %s", e)

    async def _save_to_chat_buffered(self, content: str) -> None:
        """Save output to chat with buffering (Issue #486: extracted)."""
        if not (self.chat_history_manager and self.conversation_id and content):
            return

        async with self._output_lock:
            self._output_buffer += content
            current_time = time.time()

            should_save = (
                len(self._output_buffer) > 500
                or (current_time - self._last_output_save_time) > 2.0
                or "\n" in content
            )

            if should_save and self._output_buffer.strip():
                reset_buffer, _ = await _save_buffered_output_to_chat(
                    self.chat_history_manager,
                    self.conversation_id,
                    self._output_buffer,
                )
                if reset_buffer:
                    self._output_buffer = ""
                    self._last_output_save_time = current_time

    async def send_output(self, content: str):
        """
        Enhanced output sending with standardized format (Issue #486: refactored).

        Phase 3: Uses queue-based delivery for better responsiveness.
        """
        message = self._build_output_message(content)
        await self._queue_output_message(message)
        await self._log_to_transcript(content)
        await self._save_to_chat_buffered(content)

        if self.enable_logging and content.strip():
            self._log_command_activity(
                "command_output",
                {
                    "output_length": len(content),
                    "timestamp": datetime.now().isoformat(),
                },
            )

    def _get_next_message_from_queue(self):
        """
        Get next message from output queue (Issue #315 - extracted helper).

        Returns:
            Message dict or None if queue is empty
        """
        import queue

        try:
            return self.output_queue.get_nowait()
        except queue.Empty:
            return None

    async def _send_websocket_message(self, message: dict) -> bool:
        """
        Send message to WebSocket with error handling (Issue #315 - extracted helper).

        Args:
            message: Message dict to send

        Returns:
            True if successful, False if WebSocket is closed/errored
        """
        if not (self.websocket and self.active):
            return False

        try:
            await self.websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error("Error sending queued message to WebSocket: %s", e)
            return False

    async def _async_output_sender(self):
        """
        Phase 3 Enhancement: Async task to send queued output messages to WebSocket

        This prevents the PTY reader from blocking on slow WebSocket send operations.
        Messages are queued and sent asynchronously, improving responsiveness under
        heavy terminal load.

        (Issue #315 - refactored to reduce nesting depth)
        """
        logger.info("Starting async output sender for session %s", self.session_id)

        try:
            while self.active:
                try:
                    # Non-blocking queue check using extracted helper
                    message = self._get_next_message_from_queue()

                    if message is None:
                        # No messages in queue, yield control briefly
                        await asyncio.sleep(TimingConstants.POLL_INTERVAL)
                        continue

                    # Check for stop signal (early return)
                    if message.get("type") == "stop":
                        logger.info(
                            f"Stop signal received in output sender for session {self.session_id}"
                        )
                        break

                    # Send message using extracted helper
                    success = await self._send_websocket_message(message)
                    if not success:
                        # WebSocket may be closed, stop sender
                        break

                except Exception as e:
                    logger.error("Error in async output sender loop: %s", e)
                    # Error recovery delay to prevent tight loop
                    await asyncio.sleep(TimingConstants.MICRO_DELAY)

        except Exception as e:
            logger.error("Async output sender error: %s", e)
        finally:
            logger.info("Async output sender stopped for session %s", self.session_id)


# Enhanced session manager for consolidated terminal
class ConsolidatedTerminalManager:
    """Enhanced session manager for consolidated terminal API"""

    def __init__(self):
        """Initialize manager with session tracking dictionaries."""
        self.session_configs = {}  # session_id -> config
        self.active_connections = {}  # session_id -> ConsolidatedTerminalWebSocket
        self.session_stats = {}  # session_id -> statistics
        self._lock = asyncio.Lock()  # CRITICAL: Protect concurrent dictionary access

    def add_connection(self, session_id: str, terminal: ConsolidatedTerminalWebSocket):
        """Add a WebSocket connection for a session"""
        # Note: Should be called within async context with lock acquired
        self.active_connections[session_id] = terminal
        self.session_stats[session_id] = {
            "connected_at": datetime.now(),
            "messages_sent": 0,
            "messages_received": 0,
            "commands_executed": 0,
        }

    def remove_connection(self, session_id: str):
        """Remove a WebSocket connection"""
        # Note: Should be called within async context with lock acquired
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        # Keep stats for audit purposes

    def has_connection(self, session_id: str) -> bool:
        """Check if session has active connection"""
        return session_id in self.active_connections

    async def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a session"""
        terminal = None
        async with self._lock:
            if session_id in self.active_connections:
                terminal = self.active_connections[session_id]

        if terminal:
            await terminal.send_to_terminal(text)
            # Re-acquire lock for stats update
            async with self._lock:
                if session_id in self.session_stats:
                    self.session_stats[session_id]["commands_executed"] += 1
            return True
        return False

    async def send_signal(self, session_id: str, sig: int) -> bool:
        """Send signal to a session's PTY process"""
        async with self._lock:
            terminal = self.active_connections.get(session_id)

        if terminal and terminal.pty_process:
            try:
                success = terminal.pty_process.send_signal(sig)
                if success:
                    logger.info(
                        "Sent signal %s to terminal session %s", sig, session_id
                    )
                return success
            except Exception as e:
                logger.error("Failed to send signal to session %s: %s", session_id, e)
                return False
        return False

    async def close_connection(self, session_id: str):
        """Close a session connection"""
        # CRITICAL: Atomic check-and-get with lock
        async with self._lock:
            terminal = self.active_connections.get(session_id)

        if terminal:
            await terminal.cleanup()
            # Remove connection with lock
            async with self._lock:
                self.remove_connection(session_id)

    async def get_session_stats_safe(self, session_id: str) -> dict:
        """Get statistics for a session (thread-safe)"""
        async with self._lock:
            return self.session_stats.get(session_id, {}).copy()

    def get_session_stats(self, session_id: str) -> dict:
        """Get statistics for a session"""
        # Note: For sync access, returns reference (caller should use get_session_stats_safe for
        # safety)
        return self.session_stats.get(session_id, {})

    async def get_command_history(self, session_id: str) -> list:
        """Get command history for a session"""
        async with self._lock:
            terminal = self.active_connections.get(session_id)

        if terminal:
            return [
                {
                    "command": entry["command"],
                    "timestamp": entry["timestamp"].isoformat(),
                    "risk_level": entry["risk_level"],
                }
                for entry in terminal.command_history
            ]
        return []

    async def send_output_to_conversation(
        self, conversation_id: str, content: str
    ) -> int:
        """
        Send output to all terminal WebSockets linked to a conversation.

        Args:
            conversation_id: The conversation ID to send output to
            content: The output content to send

        Returns:
            Number of terminals that received the output

        Note: This method is currently unused - PTY sessions handle terminal output automatically.
        Kept for potential future use cases where manual output routing may be needed.
        """
        # CRITICAL: Snapshot session configs under lock to prevent race conditions
        terminals_to_send = []
        async with self._lock:
            for session_id, config in list(self.session_configs.items()):
                if config.get("conversation_id") == conversation_id:
                    if session_id in self.active_connections:
                        terminals_to_send.append(
                            (session_id, self.active_connections[session_id])
                        )

        # Send outside lock to avoid blocking
        count = 0
        for session_id, terminal in terminals_to_send:
            try:
                await terminal.send_output(content)
                count += 1
                logger.debug("Sent output to terminal %s", session_id)
            except Exception as e:
                logger.error("Failed to send output to terminal %s: %s", session_id, e)
        return count

    def _get_single_session_stats(self, session_id: str) -> dict:
        """
        Build stats for a single session (Issue #665: extracted helper).

        Must be called under self._lock.
        """
        pty_session = simple_pty_manager.get_session(session_id)
        if not pty_session and session_id not in self.active_connections:
            return {"error": f"Session {session_id} not found"}

        session_stats = self.session_stats.get(session_id, {})
        uptime = 0
        if "connected_at" in session_stats:
            uptime = (datetime.now() - session_stats["connected_at"]).total_seconds()

        return {
            "session_id": session_id,
            "config": self.session_configs.get(session_id, {}),
            "is_connected": session_id in self.active_connections,
            "pty_alive": pty_session.is_alive() if pty_session else False,
            "uptime_seconds": uptime,
            "statistics": session_stats,
        }

    def _get_all_sessions_stats(self) -> dict:
        """
        Build stats for all sessions (Issue #665: extracted helper).

        Must be called under self._lock.
        """
        with simple_pty_manager._lock:
            pty_sessions = dict(simple_pty_manager.sessions)

        total_commands = sum(
            stats.get("commands_executed", 0) for stats in self.session_stats.values()
        )

        return {
            "total_sessions": len(pty_sessions),
            "active_connections": len(self.active_connections),
            "total_commands_executed": total_commands,
            "sessions": {
                sid: {
                    "is_connected": sid in self.active_connections,
                    "commands_executed": self.session_stats.get(sid, {}).get(
                        "commands_executed", 0
                    ),
                }
                for sid in pty_sessions.keys()
            },
        }

    async def get_terminal_stats(self, session_id: str = None) -> dict:
        """Get terminal statistics for a specific session or all sessions.

        Issue #665: Refactored to use _get_single_session_stats and _get_all_sessions_stats.

        Args:
            session_id: Optional session ID. If provided, returns stats for that session.
                       If None, returns overall system statistics.

        Returns:
            Dictionary containing terminal statistics.
        """
        async with self._lock:
            if session_id:
                return self._get_single_session_stats(session_id)
            return self._get_all_sessions_stats()


# Global session manager
session_manager = ConsolidatedTerminalManager()
