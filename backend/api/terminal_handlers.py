# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Handlers - WebSocket and Session Management Classes.

This module contains the core handler classes for terminal operations.
Extracted from terminal.py for better maintainability (Issue #185, #210).

Classes:
- ConsolidatedTerminalWebSocket: WebSocket handler for real-time terminal I/O
- ConsolidatedTerminalManager: Session registry and lifecycle management

Related Issues: #185 (Split), #210 (Terminal split)
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import WebSocket

from backend.services.simple_pty import simple_pty_manager

# Import models from dedicated module (Issue #185)
from backend.api.terminal_models import (
    CommandRiskLevel,
    MODERATE_RISK_PATTERNS,
    RISKY_COMMAND_PATTERNS,
    SecurityLevel,
)
from src.chat_history_manager import ChatHistoryManager
from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for shell operators (Issue #326)
SHELL_OPERATORS = {">", ">>", "|", "&&", "||"}


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
        self.websocket = websocket
        self.session_id = session_id
        self.conversation_id = conversation_id  # Link to chat session
        self.security_level = security_level
        self.enable_logging = security_level in [
            SecurityLevel.ELEVATED,
            SecurityLevel.RESTRICTED,
        ]
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
                logger.error(f"Failed to create PTY session {self.session_id}")
                self.pty_process = None

        except Exception as e:
            logger.error(f"Could not initialize PTY process: {e}")
            self.pty_process = None

    async def _read_pty_output(self):
        """Async task to read PTY output and send to WebSocket"""
        logger.info(f"Starting PTY output reader for session {self.session_id}")

        while self.active and self.pty_process:
            try:
                # Get output from PTY (non-blocking)
                output = self.pty_process.get_output()

                if output:
                    event_type, content = output

                    if event_type == "output":
                        # Send output to WebSocket
                        await self.send_output(content)
                    elif event_type in ("eo", "close"):
                        # PTY closed
                        logger.info(f"PTY closed for session {self.session_id}")
                        await self.send_message(
                            {
                                "type": "terminal_closed",
                                "content": "Terminal session ended",
                            }
                        )
                        break
                else:
                    # No output available, small delay to prevent CPU spinning
                    await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Error reading PTY output: {e}")
                break

        logger.info(f"PTY output reader stopped for session {self.session_id}")

    async def send_message(self, message: dict):
        """Send message to WebSocket client"""
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending message: {e}")

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
                logger.error(f"Error writing to PTY: {e}")
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
        logger.info(f"Async output sender started for session {self.session_id}")

        # Start PTY output reader task if PTY is available
        if self.pty_process and self.pty_process.is_alive():
            self.pty_output_task = asyncio.create_task(self._read_pty_output())
            logger.info(f"PTY output reader started for session {self.session_id}")

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
            logger.warning(f"PTY not available for session {self.session_id}")
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
                    if self._output_buffer.strip():
                        from src.utils.encoding_utils import strip_ansi_codes

                        # Strip ANSI codes before saving to chat
                        clean_content = strip_ansi_codes(self._output_buffer).strip()
                        logger.info(
                            f"[CHAT INTEGRATION] Flushing remaining output buffer on cleanup: {len(self._output_buffer)} chars (clean: {len(clean_content)} chars)"
                        )
                        if clean_content:
                            await self.chat_history_manager.add_message(
                                sender="terminal",
                                text=clean_content,  # Save cleaned output
                                message_type="terminal_output",
                                session_id=self.conversation_id,
                            )
                        self._output_buffer = ""
                        logger.info("[CHAT INTEGRATION] Buffer flushed successfully")
            except Exception as e:
                logger.error(f"Failed to flush output buffer: {e}")

        # Phase 3: Signal async output sender to stop
        if hasattr(self, "output_queue"):
            try:
                import queue

                self.output_queue.put_nowait({"type": "stop"})
            except queue.Full:
                logger.debug("Output queue full during shutdown, sender will stop via active flag")
            except Exception as e:
                logger.error(f"Error signaling output sender to stop: {e}")

        # Cancel output reader task if running
        if hasattr(self, "pty_output_task") and self.pty_output_task:
            try:
                self.pty_output_task.cancel()
                await asyncio.wait_for(self.pty_output_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.debug("Output task cancelled during normal shutdown")
            except Exception as e:
                logger.error(f"Error cancelling output task: {e}")

        # Cancel async output sender task if running
        if hasattr(self, "_output_sender_task") and self._output_sender_task:
            try:
                self._output_sender_task.cancel()
                await asyncio.wait_for(self._output_sender_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.debug("Output sender task cancelled during normal shutdown")
            except Exception as e:
                logger.error(f"Error cancelling output sender task: {e}")

        # Close PTY session using manager
        if self.pty_process:
            try:
                from backend.services.simple_pty import simple_pty_manager

                simple_pty_manager.close_session(self.session_id)
                self.pty_process = None
                logger.info(f"PTY session {self.session_id} closed")
            except Exception as e:
                logger.error(f"Error closing PTY session: {e}")

    def _get_message_handlers(self) -> Dict[str, Callable[[dict], Awaitable[None]]]:
        """Get dispatch table for message type handlers (Issue #336 - extracted helper)."""
        return {
            "input": self._handle_input_message,
            "terminal_stdin": self._handle_terminal_stdin,  # Issue #33
            "workflow_control": self._handle_workflow_control,
            "ping": self._handle_ping_message,
            "resize": self._handle_resize,
            "signal": self._handle_signal_message,
        }

    async def _handle_ping_message(self, message: dict) -> None:
        """Handle ping message (Issue #336 - extracted handler)."""
        await self.send_message({"type": "pong", "timestamp": time.time()})

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
                logger.warning(f"Unknown message type: {message_type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.send_message(
                {
                    "type": "error",
                    "content": f"Error processing message: {str(e)}",
                    "timestamp": time.time(),
                }
            )

    async def _handle_input_message(self, message: dict):
        """Handle terminal input with security assessment"""
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

        # CRITICAL FIX: Only log complete commands (when Enter is pressed)
        # Terminal sends character-by-character, we only want to log on Enter
        is_command_complete = "\r" in text or "\n" in text

        # Build command buffer for this session
        if not hasattr(self, "_command_buffer"):
            self._command_buffer = ""

        # CRITICAL: Log ALL input to transcript (character-by-character for complete record)
        if self.terminal_logger and self.conversation_id:
            try:
                transcript_file = f"{self.conversation_id}_terminal_transcript.txt"
                from pathlib import Path

                import aiofiles

                transcript_path = Path("data/chats") / transcript_file
                async with aiofiles.open(
                    transcript_path, "a", encoding="utf-8"
                ) as f:
                    await f.write(text)
            except OSError as e:
                logger.error(
                    f"Failed to write input to transcript (I/O error): {e}"
                )
            except Exception as e:
                logger.error(f"Failed to write input to transcript: {e}")

        if is_command_complete:
            # Extract command before the newline
            command = (
                (self._command_buffer + text).split("\r")[0].split("\n")[0].strip()
            )
            self._command_buffer = ""  # Reset buffer

            # Only log non-empty commands
            if not command:
                await self.send_to_terminal(text)
                return

            logger.info(
                f"[COMPLETE COMMAND] Session {self.session_id}: {repr(command)}"
            )
        else:
            # Accumulate characters until Enter is pressed
            self._command_buffer += text
            await self.send_to_terminal(text)
            return

        # Security assessment for commands
        risk_level = self._assess_command_risk(command)

        # Log command for audit trail (internal logging)
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

        # Log to TerminalLogger for persistent storage (MANUAL commands)
        logger.info(
            f"[MANUAL CMD DEBUG] terminal_logger={self.terminal_logger is not None}, "
            f"conversation_id={self.conversation_id}, command={command[:50]}"
        )
        if self.terminal_logger and self.conversation_id:
            try:
                logger.info(
                    f"[MANUAL CMD] Logging to {self.conversation_id}: {command[:50]}"
                )
                await self.terminal_logger.log_command(
                    session_id=self.conversation_id,
                    command=command,
                    run_type="manual",
                    status="executing",
                    user_id=None,
                )
                logger.info(
                    f"[MANUAL CMD] Successfully logged to {self.conversation_id}"
                )
            except Exception as e:
                logger.error(f"Failed to log command to TerminalLogger: {e}")
        else:
            logger.warning(
                f"[MANUAL CMD] Skipping log - terminal_logger={self.terminal_logger is not None}, "
                f"conversation_id={self.conversation_id}"
            )

        # CRITICAL FIX: Save command as terminal message to chat
        # Use sender="terminal" instead of "user" to prevent triggering AI responses
        if self.chat_history_manager and self.conversation_id:
            try:
                logger.info(
                    f"[CHAT INTEGRATION] Saving command to chat: {command[:50]}"
                )
                await self.chat_history_manager.add_message(
                    sender="terminal",
                    text=f"$ {command}",
                    message_type="terminal_command",
                    session_id=self.conversation_id,
                )
                logger.info("[CHAT INTEGRATION] Command saved successfully")
            except Exception as e:
                logger.error(f"Failed to save command to chat: {e}")

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
            return

        # Send to terminal (send the original text with \r to execute)
        await self.send_to_terminal(text)

        # Log command sent to terminal (completion status)
        # NOTE: For MANUAL commands, we can't easily capture output because PTY streams are async
        # Output capture works for AUTOBOT commands because they use SecureCommandExecutor
        # MANUAL commands are logged as "sent" - user can see full output in terminal interface
        if self.terminal_logger and self.conversation_id:
            try:
                await self.terminal_logger.log_command(
                    session_id=self.conversation_id,
                    command=command,
                    run_type="manual",
                    status="sent",  # Indicates command was sent to PTY
                    user_id=None,
                )
            except Exception as e:
                logger.error(f"Failed to log command completion: {e}")

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
        """
        logger.info(
            f"[STDIN] Session {self.session_id}, receiving stdin for interactive command"
        )

        # Extract stdin content
        content = message.get("content", "")
        is_password = message.get("is_password", False)
        command_id = message.get("command_id")  # For linking to approved command

        # Security: Size limit (prevent abuse)
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
            return

        # Validate PTY exists
        if not self.pty_process:
            logger.error(f"[STDIN] No PTY process for session {self.session_id}")
            await self.send_message(
                {
                    "type": "error",
                    "content": "No terminal session available",
                    "timestamp": time.time(),
                }
            )
            return

        # Disable echo for password input (Issue #33 Phase 4)
        if is_password:
            logger.info(
                f"[STDIN] Disabling echo for password input (command_id: {command_id})"
            )
            self.pty_process.set_echo(False)

        try:
            # Send stdin directly to PTY
            success = self.pty_process.write_input(content)

            if success:
                logger.info(
                    f"[STDIN] Successfully sent {len(content)} bytes to PTY "
                    f"(password: {is_password}, command_id: {command_id})"
                )

                # Re-enable echo after password (if it was disabled)
                if is_password:
                    # Wait a tiny bit for password to be processed
                    await asyncio.sleep(0.1)
                    self.pty_process.set_echo(True)
                    logger.info("[STDIN] Re-enabled echo after password input")
            else:
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

        except Exception as e:
            logger.error(f"[STDIN] Error writing to PTY: {e}")
            # Re-enable echo if it was disabled (ensure terminal doesn't stay in silent mode)
            if is_password:
                try:
                    self.pty_process.set_echo(True)
                except Exception as echo_err:
                    logger.debug(f"Failed to re-enable echo: {echo_err}")

            await self.send_message(
                {
                    "type": "error",
                    "content": f"Error sending input: {str(e)}",
                    "timestamp": time.time(),
                }
            )

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
            logger.error(f"Error resizing terminal: {e}")

    async def _handle_signal_message(self, message: dict):
        """Handle signal requests (SIGINT, SIGTERM, etc.)"""
        signal_name = message.get("signal", "SIGINT")

        try:
            # Map signal names to signal numbers
            import signal

            signal_map = {
                "SIGINT": signal.SIGINT,
                "SIGTERM": signal.SIGTERM,
                "SIGKILL": signal.SIGKILL,
                "SIGHUP": signal.SIGHUP,
            }

            sig = signal_map.get(signal_name)
            if not sig:
                logger.warning(f"Unknown signal: {signal_name}")
                await self.send_message(
                    {
                        "type": "error",
                        "content": f"Unknown signal: {signal_name}",
                        "timestamp": time.time(),
                    }
                )
                return

            # Send signal to PTY process
            if self.pty_process:
                success = self.pty_process.send_signal(sig)
                if success:
                    logger.info(f"Sent {signal_name} to PTY process")
                    await self.send_message(
                        {
                            "type": "signal_sent",
                            "signal": signal_name,
                            "timestamp": time.time(),
                        }
                    )
                else:
                    logger.error(f"Failed to send {signal_name}")
                    await self.send_message(
                        {
                            "type": "error",
                            "content": f"Failed to send signal: {signal_name}",
                            "timestamp": time.time(),
                        }
                    )
            else:
                logger.warning("No PTY process to send signal to")
                await self.send_message(
                    {
                        "type": "error",
                        "content": "No active process to interrupt",
                        "timestamp": time.time(),
                    }
                )

            if self.enable_logging:
                self._log_command_activity(
                    "signal_sent",
                    {
                        "signal": signal_name,
                        "timestamp": datetime.now().isoformat(),
                        "success": success if self.pty_process else False,
                    },
                )

        except Exception as e:
            logger.error(f"Error sending signal: {e}")
            await self.send_message(
                {
                    "type": "error",
                    "content": f"Error sending signal: {str(e)}",
                    "timestamp": time.time(),
                }
            )

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
            return risk_level in [CommandRiskLevel.DANGEROUS, CommandRiskLevel.HIGH]
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

        # Also log to system logger for persistent audit trail
        logger.info(f"Terminal audit: {json.dumps(log_entry)}")

    async def send_output(self, content: str):
        """Enhanced output sending with standardized format

        Phase 3: Uses queue-based delivery for better responsiveness.
        Messages are queued and sent asynchronously by _async_output_sender().
        """
        # Standardize message format for frontend compatibility
        message = {
            "type": "output",
            "content": content,  # Frontend expects 'content' field
            "metadata": {
                "session_id": self.session_id,
                "timestamp": time.time(),
                "terminal_type": "consolidated",
                "security_level": self.security_level.value,
            },
        }

        # Phase 3: Queue message for async delivery instead of sending directly
        # This prevents blocking on slow WebSocket send operations
        import queue

        try:
            self.output_queue.put_nowait(message)
        except queue.Full:
            # Queue is full, drop oldest message to prevent blocking
            try:
                self.output_queue.get_nowait()  # Remove oldest
                self.output_queue.put_nowait(message)  # Add new
                logger.warning(
                    f"Output queue full for session {self.session_id}, dropped oldest message"
                )
            except (queue.Empty, queue.Full):
                logger.error(f"Failed to queue output for session {self.session_id}")
        except Exception as e:
            logger.error(f"Error queuing output: {e}")
            # Fallback: Send directly if queuing fails
            await self.send_message(message)

        # CRITICAL: Log ALL terminal output to transcript file
        # This creates a complete record of the terminal session
        if self.terminal_logger and self.conversation_id and content:
            try:
                # Write raw output to transcript file
                transcript_file = f"{self.conversation_id}_terminal_transcript.txt"
                from pathlib import Path

                import aiofiles

                transcript_path = Path("data/chats") / transcript_file
                async with aiofiles.open(
                    transcript_path, "a", encoding="utf-8"
                ) as f:
                    await f.write(content)
            except OSError as e:
                logger.error(
                    f"Failed to write terminal transcript (I/O error): {e}"
                )
            except Exception as e:
                logger.error(f"Failed to write terminal transcript: {e}")

        # CRITICAL FIX: Save output to chat (buffered to avoid too many messages)
        # Protected by asyncio.Lock to prevent race conditions in concurrent scenarios
        if self.chat_history_manager and self.conversation_id and content:
            async with self._output_lock:
                # Accumulate output in buffer
                self._output_buffer += content
                current_time = time.time()

                # Save to chat when:
                # 1. Buffer is large enough (>500 chars) OR
                # 2. Enough time has passed (>2 seconds) OR
                # 3. Output contains a newline (command completed)
                should_save = (
                    len(self._output_buffer) > 500
                    or (current_time - self._last_output_save_time) > 2.0
                    or "\n" in content
                )

                # CRITICAL FIX: Strip ANSI codes and detect terminal prompts before saving
                # Prevents saving blank prompts and terminal UI elements to chat
                if should_save and self._output_buffer.strip():
                    from src.utils.encoding_utils import (
                        is_terminal_prompt,
                        strip_ansi_codes,
                    )

                    clean_content = strip_ansi_codes(self._output_buffer).strip()

                    # Check if this is a terminal prompt (not real output)
                    is_prompt = is_terminal_prompt(clean_content)

                    # Only save if there's actual text content AND it's not a terminal prompt
                    if clean_content and not is_prompt:
                        try:
                            # CRITICAL FIX: Save CLEAN content without ANSI escape codes
                            # This prevents escape codes from leaking into chat history
                            logger.info(
                                f"[CHAT INTEGRATION] Saving output to chat: {len(self._output_buffer)} chars (clean: {len(clean_content)} chars)"
                            )
                            await self.chat_history_manager.add_message(
                                sender="terminal",
                                text=clean_content,  # Save cleaned output, not raw buffer
                                message_type="terminal_output",
                                session_id=self.conversation_id,
                            )
                            # Reset buffer after saving
                            self._output_buffer = ""
                            self._last_output_save_time = current_time
                            logger.info("[CHAT INTEGRATION] Output saved successfully")
                        except Exception as e:
                            logger.error(f"Failed to save output to chat: {e}")
                    else:
                        # Buffer contains only ANSI codes or is a terminal prompt, skip saving
                        skip_reason = (
                            "terminal prompt" if is_prompt else "only ANSI codes"
                        )
                        logger.debug(
                            f"[CHAT INTEGRATION] Skipping save - buffer is {skip_reason} ({len(self._output_buffer)} chars, clean: '{clean_content[:100]}')"
                        )
                        self._output_buffer = ""
                        self._last_output_save_time = current_time

        # Log output if security logging enabled
        if self.enable_logging and len(content.strip()) > 0:
            self._log_command_activity(
                "command_output",
                {
                    "output_length": len(content),
                    "timestamp": datetime.now().isoformat(),
                },
            )

    async def _async_output_sender(self):
        """
        Phase 3 Enhancement: Async task to send queued output messages to WebSocket

        This prevents the PTY reader from blocking on slow WebSocket send operations.
        Messages are queued and sent asynchronously, improving responsiveness under
        heavy terminal load.
        """
        import queue

        logger.info(f"Starting async output sender for session {self.session_id}")

        try:
            while self.active:
                try:
                    # Non-blocking queue check
                    try:
                        message = self.output_queue.get_nowait()
                    except queue.Empty:
                        # No messages in queue, yield control briefly
                        await asyncio.sleep(0.01)
                        continue

                    # Check for stop signal
                    if message.get("type") == "stop":
                        logger.info(
                            f"Stop signal received in output sender for session {self.session_id}"
                        )
                        break

                    # Send message if WebSocket is still active
                    if self.websocket and self.active:
                        try:
                            await self.websocket.send_text(json.dumps(message))
                        except Exception as e:
                            logger.error(
                                f"Error sending queued message to WebSocket: {e}"
                            )
                            # WebSocket may be closed, stop sender
                            break

                except Exception as e:
                    logger.error(f"Error in async output sender loop: {e}")
                    await asyncio.sleep(0.1)  # Prevent tight error loop

        except Exception as e:
            logger.error(f"Async output sender error: {e}")
        finally:
            logger.info(f"Async output sender stopped for session {self.session_id}")


# Enhanced session manager for consolidated terminal
class ConsolidatedTerminalManager:
    """Enhanced session manager for consolidated terminal API"""

    def __init__(self):
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
                    logger.info(f"Sent signal {sig} to terminal session {session_id}")
                return success
            except Exception as e:
                logger.error(f"Failed to send signal to session {session_id}: {e}")
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
                logger.debug(f"Sent output to terminal {session_id}")
            except Exception as e:
                logger.error(f"Failed to send output to terminal {session_id}: {e}")
        return count

    async def get_terminal_stats(self, session_id: str = None) -> dict:
        """Get terminal statistics for a specific session or all sessions

        Args:
            session_id: Optional session ID. If provided, returns stats for that session.
                       If None, returns overall system statistics.

        Returns:
            Dictionary containing terminal statistics including:
            - Session counts (total, active)
            - Per-session statistics (if session_id provided)
            - Overall system metrics
        """
        # CRITICAL: Access all dictionaries under lock to prevent race conditions
        async with self._lock:
            if session_id:
                # Return stats for specific session
                # Use simple_pty_manager instead of non-existent self.sessions
                pty_session = simple_pty_manager.get_session(session_id)
                if not pty_session and session_id not in self.active_connections:
                    return {"error": f"Session {session_id} not found"}

                session_stats = self.session_stats.get(session_id, {})

                # Calculate uptime
                uptime = 0
                if "connected_at" in session_stats:
                    uptime = (
                        datetime.now() - session_stats["connected_at"]
                    ).total_seconds()

                return {
                    "session_id": session_id,
                    "config": self.session_configs.get(session_id, {}),
                    "is_connected": session_id in self.active_connections,
                    "pty_alive": pty_session.is_alive() if pty_session else False,
                    "uptime_seconds": uptime,
                    "statistics": session_stats,
                }
            else:
                # Return overall system statistics
                # Use simple_pty_manager.sessions with its lock
                with simple_pty_manager._lock:
                    pty_sessions = dict(simple_pty_manager.sessions)

                total_sessions = len(pty_sessions)
                active_connections = len(self.active_connections)
                total_commands = sum(
                    stats.get("commands_executed", 0)
                    for stats in self.session_stats.values()
                )

                return {
                    "total_sessions": total_sessions,
                    "active_connections": active_connections,
                    "total_commands_executed": total_commands,
                    "sessions": {
                        sid: {
                            "is_connected": sid in self.active_connections,
                            "commands_executed": (
                                self.session_stats.get(sid, {}).get(
                                    "commands_executed", 0
                                )
                            ),
                        }
                        for sid in pty_sessions.keys()
                    },
                }


# Global session manager
session_manager = ConsolidatedTerminalManager()
