"""
Terminal API - Unified Terminal System for AutoBot

This module provides the core terminal infrastructure used by both Tools Terminal
and Chat Terminal. It implements WebSocket-based PTY (pseudo-terminal) access with
real-time bidirectional communication.

Architecture:
-----------
┌────────────────────────────────────────────────────────────┐
│ Tools Terminal (Standalone) │ Chat Terminal (AI-Integrated)│
└────────────┬────────────────┴──────────────┬───────────────┘
             │                               │
             │  Both use this module         │
             └───────────────┬───────────────┘
                             │
         ┌───────────────────▼────────────────────┐
         │  backend/api/terminal.py               │
         │  • REST API for session management     │
         │  • WebSocket for real-time I/O         │
         │  • PTY process management              │
         │  • Output buffering for chat           │
         └───────────────────┬────────────────────┘
                             │
         ┌───────────────────▼────────────────────┐
         │  backend/services/simple_pty.py        │
         │  • Real PTY creation (pty.openpty())   │
         │  • /bin/bash process spawning          │
         │  • Input/output queues                 │
         └────────────────────────────────────────┘

Key Components:
--------------
1. ConsolidatedTerminalWebSocket
   - WebSocket handler for real-time terminal I/O
   - Manages PTY process lifecycle
   - Buffers output for chat integration
   - Sends output to ChatHistoryManager when linked to conversation

2. ConsolidatedTerminalManager
   - Session registry and lifecycle management
   - Signal handling (SIGINT, SIGTERM, etc.)
   - Session cleanup and resource management

3. REST API Endpoints
   - POST /api/terminal/sessions - Create new session
   - GET /api/terminal/sessions - List active sessions
   - GET /api/terminal/sessions/{id} - Get session details
   - POST /api/terminal/sessions/{id}/input - Send input
   - POST /api/terminal/sessions/{id}/signal/{name} - Send signal
   - GET /api/terminal/sessions/{id}/history - Get command history

4. WebSocket Endpoints
   - /api/terminal/ws/{session_id} - Primary WebSocket endpoint
   - /api/terminal/ws/simple/{session_id} - Simple WebSocket (legacy)
   - /api/terminal/ws/secure/{session_id} - Secure WebSocket (legacy)

Message Protocol:
----------------
Client → Server:
    {"type": "input", "text": "ls -la\\n"}
    {"type": "resize", "rows": 24, "cols": 80}
    {"type": "ping"}

Server → Client:
    {"type": "output", "content": "file1.txt\\nfile2.txt\\n"}
    {"type": "connected", "content": "Connected to terminal"}
    {"type": "error", "content": "Terminal error message"}
    {"type": "pong"}

Chat Integration:
----------------
When conversation_id is provided:
1. All terminal output is buffered
2. Output saved to ChatHistoryManager every 500ms or 1000 chars
3. Commands logged with TerminalLogger
4. Provides complete terminal transcript in chat history

Usage Examples:
--------------
# Tools Terminal (Standalone)
1. POST /api/terminal/sessions
   → { session_id, websocket_url }
2. WebSocket /api/terminal/ws/{session_id}
3. Send/receive terminal I/O

# Chat Terminal (AI-Integrated)
1. POST /api/agent-terminal/sessions (creates agent session)
   → { session_id, pty_session_id }
2. WebSocket /api/terminal/ws/{pty_session_id} (uses this module)
3. Output automatically saved to chat history

Security:
--------
- Command validation via SecureCommandExecutor (optional)
- Security levels: STANDARD, ELEVATED, RESTRICTED
- Audit logging for sensitive operations
- Session isolation (each PTY is independent)

See Also:
--------
- backend/api/agent_terminal.py - Agent terminal with approval workflow
- backend/services/agent_terminal_service.py - Agent terminal business logic
- backend/services/simple_pty.py - PTY implementation
- docs/architecture/TERMINAL_ARCHITECTURE_DIAGRAM.md - Architecture details
"""

import asyncio
import json
import logging
import signal
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.chat_history_manager import ChatHistoryManager
from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PATH
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Create router for consolidated terminal API
router = APIRouter(tags=["terminal"])


class SecurityLevel(Enum):
    """Security levels for terminal access"""

    STANDARD = "standard"
    ELEVATED = "elevated"
    RESTRICTED = "restricted"


class CommandRiskLevel(Enum):
    """Risk assessment levels for commands"""

    SAFE = "safe"
    MODERATE = "moderate"
    HIGH = "high"
    DANGEROUS = "dangerous"


# Request/Response Models
class CommandRequest(BaseModel):
    command: str
    description: Optional[str] = None
    require_confirmation: Optional[bool] = True
    timeout: Optional[float] = 30.0
    working_directory: Optional[str] = None
    environment: Optional[Dict[str, str]] = None


class TerminalSessionRequest(BaseModel):
    user_id: Optional[str] = "default"
    conversation_id: Optional[str] = None  # Link to chat session for logging
    security_level: Optional[SecurityLevel] = SecurityLevel.STANDARD
    enable_logging: Optional[bool] = True
    enable_workflow_control: Optional[bool] = True
    initial_directory: Optional[str] = None


class TerminalInputRequest(BaseModel):
    text: str
    is_password: Optional[bool] = False


class WorkflowControlRequest(BaseModel):
    action: str  # pause, resume, approve_step, cancel
    workflow_id: Optional[str] = None
    step_id: Optional[str] = None
    data: Optional[Dict] = None


class ToolInstallRequest(BaseModel):
    tool_name: str
    package_name: Optional[str] = None
    install_method: Optional[str] = "auto"
    custom_command: Optional[str] = None
    update_first: Optional[bool] = True


# Security patterns for command risk assessment
RISKY_COMMAND_PATTERNS = [
    # File system destructive operations
    "rm -r",
    "rm -rf",
    "sudo rm",
    "rmdir",
    # Disk operations
    "dd if=",
    "mkfs",
    "fdisk",
    "parted",
    # Permission changes
    "chmod 777",
    "chmod -R 777",
    "chown -R",
    # System-level operations
    "> /dev/",
    "/dev/sda",
    "/dev/sdb",
    # Network security
    "iptables -F",
    "ufw disable",
    # System shutdown
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    # Package management (can be risky)
    "apt-get remove",
    "yum remove",
    "rm /etc/",
    # Process killing
    "kill -9",
    "killall -9",
]

MODERATE_RISK_PATTERNS = [
    "sudo",
    "su -",
    "chmod",
    "chown",
    "apt-get install",
    "yum install",
    "pip install",
    "systemctl",
    "service",
    "mount",
    "umount",
]


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
                    elif event_type in ("eof", "close"):
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
        logger.info(
            f"Async output sender started for session {self.session_id}"
        )

        # Start PTY output reader task if PTY is available
        if self.pty_process and self.pty_process.is_alive():
            self.pty_output_task = asyncio.create_task(self._read_pty_output())
            logger.info(f"PTY output reader started for session {self.session_id}")

            # NOTE: Keep PTY echo ON by default for automated/agent mode visibility
            # Frontend handles local echo for manual mode to reduce lag
            # This ensures agent commands are visible to user in automated mode
            logger.info(f"PTY echo enabled for session {self.session_id} (agent commands visible)")

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
                        logger.info(f"[CHAT INTEGRATION] Buffer flushed successfully")
            except Exception as e:
                logger.error(f"Failed to flush output buffer: {e}")

        # Phase 3: Signal async output sender to stop
        if hasattr(self, "output_queue"):
            try:
                import queue

                self.output_queue.put_nowait({"type": "stop"})
            except queue.Full:
                pass  # Queue full, sender will stop when it checks active flag
            except Exception as e:
                logger.error(f"Error signaling output sender to stop: {e}")

        # Cancel output reader task if running
        if hasattr(self, "pty_output_task") and self.pty_output_task:
            try:
                self.pty_output_task.cancel()
                await asyncio.wait_for(self.pty_output_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.error(f"Error cancelling output task: {e}")

        # Cancel async output sender task if running
        if hasattr(self, "_output_sender_task") and self._output_sender_task:
            try:
                self._output_sender_task.cancel()
                await asyncio.wait_for(self._output_sender_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
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

            if message_type == "input":
                await self._handle_input_message(message)
            elif message_type == "terminal_stdin":  # Issue #33 - Interactive stdin
                await self._handle_terminal_stdin(message)
            elif message_type == "workflow_control":
                await self._handle_workflow_control(message)
            elif message_type == "ping":
                await self.send_message({"type": "pong", "timestamp": time.time()})
            elif message_type == "resize":
                await self._handle_resize(message)
            elif message_type == "signal":
                await self._handle_signal_message(message)
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
                f"[_handle_input_message] No text found in message, returning"
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
                async with aiofiles.open(transcript_path, "a") as f:
                    await f.write(text)
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
                logger.info(f"[CHAT INTEGRATION] Command saved successfully")
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
                    "content": f"Command blocked due to {risk_level.value} "
                    f"risk level: {command}",
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
            await self.send_message({
                "type": "error",
                "content": f"Input too large (max {MAX_STDIN_SIZE} bytes)",
                "timestamp": time.time(),
            })
            return

        # Validate PTY exists
        if not self.pty_process:
            logger.error(f"[STDIN] No PTY process for session {self.session_id}")
            await self.send_message({
                "type": "error",
                "content": "No terminal session available",
                "timestamp": time.time(),
            })
            return

        # Disable echo for password input (Issue #33 Phase 4)
        if is_password:
            logger.info(f"[STDIN] Disabling echo for password input (command_id: {command_id})")
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
                    logger.info(f"[STDIN] Re-enabled echo after password input")
            else:
                logger.error(f"[STDIN] Failed to write to PTY for session {self.session_id}")
                await self.send_message({
                    "type": "error",
                    "content": "Failed to send input to terminal",
                    "timestamp": time.time(),
                })

        except Exception as e:
            logger.error(f"[STDIN] Error writing to PTY: {e}")
            # Re-enable echo if it was disabled (ensure terminal doesn't stay in silent mode)
            if is_password:
                try:
                    self.pty_process.set_echo(True)
                except:
                    pass

            await self.send_message({
                "type": "error",
                "content": f"Error sending input: {str(e)}",
                "timestamp": time.time(),
            })

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

        # Special checks for high-risk operations
        if any(x in command_lower for x in [">", ">>", "|", "&&", "||"]):
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
                logger.error(
                    f"Failed to queue output for session {self.session_id}"
                )
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
                async with aiofiles.open(transcript_path, "a") as f:
                    await f.write(content)
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
                    from src.utils.encoding_utils import strip_ansi_codes, is_terminal_prompt

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
                            logger.info(f"[CHAT INTEGRATION] Output saved successfully")
                        except Exception as e:
                            logger.error(f"Failed to save output to chat: {e}")
                    else:
                        # Buffer contains only ANSI codes or is a terminal prompt, skip saving
                        skip_reason = "terminal prompt" if is_prompt else "only ANSI codes"
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

        logger.info(
            f"Starting async output sender for session {self.session_id}"
        )

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
            logger.info(
                f"Async output sender stopped for session {self.session_id}"
            )


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
                    logger.info(
                        f"Sent signal {sig} to terminal session {session_id}"
                    )
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
        # Note: For sync access, returns reference (caller should use get_session_stats_safe for safety)
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
                        terminals_to_send.append((session_id, self.active_connections[session_id]))

        # Send outside lock to avoid blocking
        count = 0
        for session_id, terminal in terminals_to_send:
            try:
                await terminal.send_output(content)
                count += 1
                logger.debug(f"Sent output to terminal {session_id}")
            except Exception as e:
                logger.error(
                    f"Failed to send output to terminal {session_id}: {e}"
                )
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
                    uptime = (datetime.now() - session_stats["connected_at"]).total_seconds()

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
                            "commands_executed": self.session_stats.get(sid, {}).get(
                                "commands_executed", 0
                            ),
                        }
                        for sid in pty_sessions.keys()
                    },
                }


# Global session manager
session_manager = ConsolidatedTerminalManager()

# REST API Endpoints


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_terminal_session",
    error_code_prefix="TERMINAL",
)
@router.post("/sessions")
async def create_terminal_session(request: TerminalSessionRequest):
    """Create a new terminal session with enhanced security options"""
    session_id = str(uuid.uuid4())

    # Store session configuration for WebSocket connection
    session_config = {
        "session_id": session_id,
        "user_id": request.user_id,
        "conversation_id": request.conversation_id,  # For linking chat to terminal logging
        "security_level": request.security_level,
        "enable_logging": request.enable_logging,
        "enable_workflow_control": request.enable_workflow_control,
        "initial_directory": request.initial_directory,
        "created_at": datetime.now().isoformat(),
    }

    # Store in session manager (you would use a proper store in production)
    session_manager.session_configs[session_id] = session_config

    logger.info(f"Created terminal session: {session_id}")

    return {
        "session_id": session_id,
        "status": "created",
        "security_level": request.security_level.value,
        "websocket_url": f"/api/terminal/ws/{session_id}",
        "created_at": session_config["created_at"],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_terminal_sessions",
    error_code_prefix="TERMINAL",
)
@router.get("/sessions")
async def list_terminal_sessions():
    """List all active terminal sessions"""
    sessions = []
    for session_id, config in session_manager.session_configs.items():
        is_active = session_manager.has_connection(session_id)
        sessions.append(
            {
                "session_id": session_id,
                "user_id": config.get("user_id"),
                "security_level": config.get("security_level"),
                "created_at": config.get("created_at"),
                "is_active": is_active,
            }
        )

    return {
        "sessions": sessions,
        "total": len(sessions),
        "active": sum(1 for s in sessions if s["is_active"]),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_session",
    error_code_prefix="TERMINAL",
)
@router.get("/sessions/{session_id}")
async def get_terminal_session(session_id: str):
    """Get information about a specific terminal session"""
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail="Session not found")

    is_active = session_manager.has_connection(session_id)

    # Get session statistics if active
    stats = {}
    if is_active and hasattr(session_manager, "get_session_stats"):
        stats = session_manager.get_session_stats(session_id)

    return {
        "session_id": session_id,
        "config": config,
        "is_active": is_active,
        "statistics": stats,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_terminal_session",
    error_code_prefix="TERMINAL",
)
@router.delete("/sessions/{session_id}")
async def delete_terminal_session(session_id: str):
    """Delete a terminal session and close any active connections"""
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail="Session not found")

    # Close WebSocket connection if active
    if session_manager.has_connection(session_id):
        await session_manager.close_connection(session_id)

    # Remove session configuration
    del session_manager.session_configs[session_id]

    logger.info(f"Deleted terminal session: {session_id}")

    return {"session_id": session_id, "status": "deleted"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_single_command",
    error_code_prefix="TERMINAL",
)
@router.post("/command")
async def execute_single_command(request: CommandRequest):
    """Execute a single command with security assessment"""
    # Assess command for security risk

    # Assess command risk
    risk_level = CommandRiskLevel.SAFE
    command_lower = request.command.lower().strip()

    for pattern in RISKY_COMMAND_PATTERNS:
        if pattern in command_lower:
            risk_level = CommandRiskLevel.DANGEROUS
            break
    else:
        for pattern in MODERATE_RISK_PATTERNS:
            if pattern in command_lower:
                risk_level = CommandRiskLevel.MODERATE
                break

    # Log command execution attempt
    logger.info(
        f"Single command execution: {request.command} (risk: {risk_level.value})"
    )

    # For now, return the assessment (actual execution would need subprocess)
    return {
        "command": request.command,
        "risk_level": risk_level.value,
        "status": "assessed",
        "message": f"Command assessed as {risk_level.value} risk",
        "requires_confirmation": risk_level != CommandRiskLevel.SAFE,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_terminal_input",
    error_code_prefix="TERMINAL",
)
@router.post("/sessions/{session_id}/input")
async def send_terminal_input(session_id: str, request: TerminalInputRequest):
    """Send input to a specific terminal session"""
    if not session_manager.has_connection(session_id):
        raise HTTPException(status_code=404, detail="Session not active")

    # Send input to the WebSocket connection
    # This would be implemented through the session manager
    success = await session_manager.send_input(session_id, request.text)

    if success:
        return {
            "session_id": session_id,
            "status": "sent",
            "input": request.text if not request.is_password else "***",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to send input")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_terminal_signal",
    error_code_prefix="TERMINAL",
)
@router.post("/sessions/{session_id}/signal/{signal_name}")
async def send_terminal_signal(session_id: str, signal_name: str):
    """Send a signal to a terminal session"""
    if not session_manager.has_connection(session_id):
        raise HTTPException(status_code=404, detail="Session not active")

    # Map signal names to signal constants
    signal_map = {
        "SIGINT": signal.SIGINT,
        "SIGTERM": signal.SIGTERM,
        "SIGKILL": signal.SIGKILL,
        "SIGSTOP": signal.SIGSTOP,
        "SIGCONT": signal.SIGCONT,
    }

    if signal_name not in signal_map:
        raise HTTPException(status_code=400, detail=f"Invalid signal: {signal_name}")

    success = await session_manager.send_signal(session_id, signal_map[signal_name])

    if success:
        return {"session_id": session_id, "signal": signal_name, "status": "sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send signal")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_command_history",
    error_code_prefix="TERMINAL",
)
@router.get("/sessions/{session_id}/history")
async def get_terminal_command_history(session_id: str):
    """Get command history for a terminal session"""
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if session has active connection
    is_active = session_manager.has_connection(session_id)

    if not is_active:
        return {
            "session_id": session_id,
            "is_active": False,
            "history": [],
            "message": "Session is not active, no command history available",
        }

    # Get command history from active terminal
    history = session_manager.get_command_history(session_id)

    return {
        "session_id": session_id,
        "is_active": True,
        "history": history,
        "total_commands": len(history),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_audit_log",
    error_code_prefix="TERMINAL",
)
@router.get("/audit/{session_id}")
async def get_session_audit_log(session_id: str):
    """Get security audit log for a session (elevated access required)"""
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail="Session not found")

    # In a real implementation, you'd check user permissions here
    # For now, return basic audit information

    return {
        "session_id": session_id,
        "audit_available": config.get("enable_logging", False),
        "security_level": config.get("security_level"),
        "message": "Audit log access requires elevated permissions",
    }


# WebSocket Endpoints


@router.websocket("/ws/{session_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="consolidated_terminal_websocket",
    error_code_prefix="TERMINAL",
)
async def consolidated_terminal_websocket(websocket: WebSocket, session_id: str):
    """
    Primary WebSocket endpoint for consolidated terminal access
    Replaces both /ws/simple and /ws/secure endpoints
    """
    await websocket.accept()

    try:
        # Get session configuration
        config = session_manager.session_configs.get(session_id, {})
        security_level = SecurityLevel(
            config.get("security_level", SecurityLevel.STANDARD.value)
        )
        conversation_id = config.get("conversation_id")  # For chat/terminal linking

        # Get Redis client for TerminalLogger
        redis_client = None
        try:
            from backend.dependencies import get_redis_client

            redis_client = get_redis_client()
        except Exception as e:
            logger.warning(f"Could not get Redis client for terminal logging: {e}")

        # Create consolidated terminal handler
        terminal = ConsolidatedTerminalWebSocket(
            websocket, session_id, security_level, conversation_id, redis_client
        )

        # Register with session manager
        session_manager.add_connection(session_id, terminal)

        # Start terminal session (activates PTY output reader)
        await terminal.start()

        logger.info(f"WebSocket connection established for session {session_id}")

        # Handle WebSocket communication
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                logger.info(
                    f"[WS RECV] Session {session_id}, Type: {message.get('type')}, Data: {str(message)[:100]}"
                )
                await terminal.handle_message(message)

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for session {session_id}")
        except Exception as e:
            logger.error(f"Error in WebSocket handling: {e}")
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "content": f"Terminal error: {str(e)}",
                        "timestamp": time.time(),
                    }
                )
            )

    except Exception as e:
        logger.error(f"Error establishing WebSocket connection: {e}")
    finally:
        # Clean up connection
        session_manager.remove_connection(session_id)
        if "terminal" in locals():
            await terminal.cleanup()


# Backward compatibility endpoints


@router.websocket("/ws/simple/{session_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="simple_terminal_websocket_compat",
    error_code_prefix="TERMINAL",
)
async def simple_terminal_websocket_compat(websocket: WebSocket, session_id: str):
    """Backward compatibility for simple terminal WebSocket"""
    # Set session to standard security for compatibility
    if session_id not in session_manager.session_configs:
        session_manager.session_configs[session_id] = {
            "session_id": session_id,
            "security_level": SecurityLevel.STANDARD,
            "enable_logging": False,
            "enable_workflow_control": True,
            "created_at": datetime.now().isoformat(),
        }

    # Route to main WebSocket handler
    await consolidated_terminal_websocket(websocket, session_id)


@router.websocket("/ws/secure/{session_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="secure_terminal_websocket_compat",
    error_code_prefix="TERMINAL",
)
async def secure_terminal_websocket_compat(websocket: WebSocket, session_id: str):
    """Backward compatibility for secure terminal WebSocket"""
    # Set session to elevated security for compatibility
    if session_id not in session_manager.session_configs:
        session_manager.session_configs[session_id] = {
            "session_id": session_id,
            "security_level": SecurityLevel.ELEVATED,
            "enable_logging": True,
            "enable_workflow_control": True,
            "created_at": datetime.now().isoformat(),
        }

    # Route to main WebSocket handler
    await consolidated_terminal_websocket(websocket, session_id)


# Tool Management endpoints


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="install_tool",
    error_code_prefix="TERMINAL",
)
@router.post("/terminal/install-tool")
async def install_tool(request: ToolInstallRequest):
    """Install a tool with terminal streaming"""
    # Import system command agent for tool installation
    from src.agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()

    tool_info = {
        "name": request.tool_name,
        "package_name": request.package_name or request.tool_name,
        "install_method": request.install_method,
        "custom_command": request.custom_command,
        "update_first": request.update_first,
    }

    result = await system_command_agent.install_tool(tool_info, "default")
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_tool_installed",
    error_code_prefix="TERMINAL",
)
@router.post("/terminal/check-tool")
async def check_tool_installed(tool_name: str):
    """Check if a tool is installed"""
    from src.agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()
    result = await system_command_agent.check_tool_installed(tool_name)
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validate_command",
    error_code_prefix="TERMINAL",
)
@router.post("/terminal/validate-command")
async def validate_command(command: str):
    """Validate command safety"""
    from src.agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()
    result = await system_command_agent.validate_command_safety(command)
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_package_managers",
    error_code_prefix="TERMINAL",
)
@router.get("/terminal/package-managers")
async def get_package_managers():
    """Get available package managers"""
    from src.agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()
    detected = await system_command_agent.detect_package_manager()
    all_managers = list(system_command_agent.PACKAGE_MANAGERS.keys())

    return {
        "detected": detected,
        "available": all_managers,
        "package_managers": system_command_agent.PACKAGE_MANAGERS,
    }


# Information endpoints


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="terminal_info",
    error_code_prefix="TERMINAL",
)
@router.get("/")
async def terminal_info():
    """Get information about the consolidated terminal API"""
    return {
        "name": "Consolidated Terminal API",
        "version": "1.0.0",
        "description": "Unified terminal API combining all previous implementations",
        "features": [
            "REST API for session management",
            "WebSocket-based real-time terminal access",
            "Security assessment and command auditing",
            "Workflow automation control integration",
            "Multi-level security controls",
            "Backward compatibility with existing endpoints",
        ],
        "endpoints": {
            "sessions": "/api/terminal/sessions",
            "websocket_primary": "/api/terminal/ws/{session_id}",
            "websocket_simple": "/api/terminal/ws/simple/{session_id}",
            "websocket_secure": "/api/terminal/ws/secure/{session_id}",
        },
        "security_levels": [level.value for level in SecurityLevel],
        "consolidated_from": [
            "terminal.py",
            "simple_terminal_websocket.py",
            "secure_terminal_websocket.py",
            "base_terminal.py",
        ],
    }


# Health and Status endpoints


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="terminal_health_check",
    error_code_prefix="TERMINAL",
)
@router.get("/health")
async def terminal_health_check():
    """Health check for consolidated terminal system

    Returns:
        Health status of all terminal components including:
        - Consolidated terminal manager
        - WebSocket manager
        - PTY system (SimplePTY)
        - Session management
    """
    try:
        # Check if manager is operational
        active_sessions = len(manager.sessions)

        return {
            "status": "healthy",
            "service": "consolidated_terminal_system",
            "components": {
                "terminal_manager": "operational",
                "websocket_manager": "operational",
                "pty_system": "operational",
                "session_manager": "operational",
            },
            "metrics": {
                "active_sessions": active_sessions,
                "manager_initialized": manager is not None,
            },
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "consolidated_terminal_system",
            "error": str(e),
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_system_status",
    error_code_prefix="TERMINAL",
)
@router.get("/status")
async def get_terminal_system_status():
    """Get overall terminal system status and configuration

    Returns:
        System status including:
        - Operational status
        - Supported terminal types (Tools Terminal, Chat Terminal)
        - Available features
        - Session statistics
    """
    try:
        return {
            "status": "operational",
            "terminal_types": ["tools_terminal", "chat_terminal"],
            "features": {
                "pty_support": True,
                "websocket_support": True,
                "command_validation": True,
                "security_policies": True,
                "approval_workflow": True,  # Chat Terminal feature
                "agent_integration": True,  # Chat Terminal feature
            },
            "session_info": {
                "active_sessions": len(manager.sessions),
                "max_concurrent_sessions": None,  # No hard limit
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_capabilities",
    error_code_prefix="TERMINAL",
)
@router.get("/capabilities")
async def get_terminal_capabilities():
    """Get terminal system capabilities

    Returns:
        Detailed list of all capabilities supported by the consolidated
        terminal system, including PTY management, WebSocket streaming,
        security validation, and more.
    """
    return {
        "pty_management": True,
        "websocket_streaming": True,
        "command_execution": True,
        "security_validation": True,
        "session_management": True,
        "terminal_types": {
            "tools_terminal": {
                "description": "Standalone system terminal for direct command execution",
                "features": ["direct_execution", "no_approval", "system_admin"],
            },
            "chat_terminal": {
                "description": "AI-integrated terminal with approval workflow",
                "features": [
                    "approval_workflow",
                    "risk_assessment",
                    "agent_integration",
                    "chat_history_logging",
                    "user_takeover",
                ],
            },
        },
        "pty_features": {
            "echo_control": True,
            "terminal_resize": True,
            "signal_handling": True,
            "queue_based_io": True,
            "non_blocking_output": True,
        },
        "websocket_features": {
            "real_time_streaming": True,
            "bidirectional_communication": True,
            "multiple_connection_types": ["primary", "simple", "secure"],
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_policies",
    error_code_prefix="TERMINAL",
)
@router.get("/security")
async def get_security_policies():
    """Get terminal security policies and command validation info

    Returns:
        Security configuration including:
        - Command validation settings
        - Risk assessment levels
        - Blocked command categories
        - Security executor information
    """
    return {
        "command_validation": "enabled",
        "risk_assessment": "multi-level",
        "risk_levels": {
            "SAFE": "Commands that are safe to execute automatically",
            "MODERATE": "Commands that require logging but are generally safe",
            "HIGH": "Potentially dangerous commands requiring approval",
            "FORBIDDEN": "Commands that are blocked completely",
        },
        "security_executor": "SecureCommandExecutor",
        "approval_workflow": {
            "enabled_for": "chat_terminal",
            "disabled_for": "tools_terminal",
            "approval_required_for": ["HIGH", "FORBIDDEN"],
        },
        "audit_logging": {
            "enabled": True,
            "logs_to": "chat_history",
            "includes": ["command", "output", "risk_level", "user_approval"],
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_features",
    error_code_prefix="TERMINAL",
)
@router.get("/features")
async def get_terminal_features():
    """Get available terminal features and implementation details

    Returns:
        Comprehensive feature list including:
        - Terminal implementations (Tools, Chat)
        - Feature descriptions
        - Technical capabilities
        - Integration points
    """
    return {
        "manager_class": "ConsolidatedTerminalManager",
        "websocket_class": "ConsolidatedTerminalWebSocket",
        "pty_implementation": "SimplePTY",
        "implementations": [
            {
                "name": "tools_terminal",
                "description": "Standalone system terminal for direct administration",
                "frontend_component": "ToolsTerminal.vue",
                "backend_api": "terminal.py (direct)",
                "approval_workflow": False,
            },
            {
                "name": "chat_terminal",
                "description": "AI-integrated terminal with command approval workflow",
                "frontend_component": "ChatTerminal.vue",
                "backend_api": "agent_terminal.py + terminal.py",
                "approval_workflow": True,
                "service_layer": "agent_terminal_service.py",
            },
        ],
        "features": {
            "pty_shell": "Full PTY shell support with SimplePTY implementation",
            "websocket_streaming": "Real-time bidirectional communication via WebSocket",
            "security_validation": "Command risk assessment via SecureCommandExecutor",
            "session_cleanup": "Proper resource cleanup on disconnect",
            "approval_workflow": "User approval for high-risk commands (Chat Terminal)",
            "agent_integration": "AI agent command execution with chat logging",
            "multi_host_support": "Execute on different hosts (main, frontend, etc.)",
        },
        "shared_infrastructure": {
            "websocket_transport": "terminal.py WebSocket endpoints",
            "pty_layer": "simple_pty.py (SimplePTY class)",
            "security": "SecureCommandExecutor for risk assessment",
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_statistics",
    error_code_prefix="TERMINAL",
)
@router.get("/stats")
async def get_terminal_statistics(session_id: str = None):
    """Get terminal statistics for specific session or all sessions

    Args:
        session_id: Optional query parameter. If provided, returns stats for that
                   specific session. If omitted, returns overall system statistics.

    Returns:
        Terminal statistics including:
        - Overall system metrics (if session_id not provided)
        - Per-session statistics (if session_id provided)
        - Session counts, command counts, uptime, etc.

    Examples:
        GET /api/terminal/stats - Get overall system statistics
        GET /api/terminal/stats?session_id=abc123 - Get stats for session abc123
    """
    return manager.get_terminal_stats(session_id)
