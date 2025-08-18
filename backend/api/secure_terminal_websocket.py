"""
Secure Terminal WebSocket Handler with Command Auditing
Provides PTY terminal with enhanced security logging and optional sandboxing
"""

import json
import logging
import time
from typing import Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from .base_terminal import BaseTerminalWebSocket

logger = logging.getLogger(__name__)


class SecureTerminalSession(BaseTerminalWebSocket):
    """Secure terminal session with command auditing and optional sandboxing"""

    def __init__(self, session_id: str, security_layer=None, user_role: str = "user"):
        super().__init__()
        self.session_id = session_id
        self.security_layer = security_layer
        self.user_role = user_role

        # Security settings
        self.audit_commands = True
        self.log_all_output = False

        # Command buffer for audit logging
        self.command_buffer = ""
        self.last_command = ""

    @property
    def terminal_type(self) -> str:
        """Get terminal type for logging"""
        return "Secure terminal"

    async def connect(self, websocket: WebSocket):
        """Connect WebSocket to this session and start PTY shell"""
        await websocket.accept()
        self.websocket = websocket
        self.active = True

        # Start PTY shell process
        await self.start_pty_shell()

        # Send connection confirmation with security status
        security_status = "enabled" if self.security_layer else "disabled"
        await self.send_message(
            {
                "type": "connection",
                "status": "connected",
                "message": f"Secure terminal connected (security: {security_status})",
                "session_id": self.session_id,
                "working_dir": self.current_dir,
                "user_role": self.user_role,
                "security": {
                    "audit_enabled": self.audit_commands,
                    "logging_enabled": self.log_all_output,
                },
            }
        )

    # PTY shell startup now handled by base class

    def process_output(self, output: str) -> str:
        """Process PTY output with security logging"""
        # Log output if enabled
        if self.log_all_output and self.security_layer:
            self.security_layer.audit_log(
                action="terminal_output",
                user=f"terminal_{self.session_id}",
                outcome="logged",
                details={"output": output, "user_role": self.user_role},
            )
        return output

    async def process_input(self, text: str) -> str:
        """Process input with security auditing"""
        # Track command input for auditing
        if "\n" in text or "\r" in text:
            # Command completed
            command = self.command_buffer + text.replace("\n", "").replace("\r", "")
            if command.strip() and self.audit_commands:
                await self.audit_command(command.strip())
            self.command_buffer = ""
        else:
            self.command_buffer += text

        return text

    async def audit_command(self, command: str):
        """Audit a command execution for security logging"""
        if not self.security_layer:
            return

        self.last_command = command

        try:
            # Log command attempt
            self.security_layer.audit_log(
                action="terminal_command",
                user=f"terminal_{self.session_id}",
                outcome="executed",
                details={
                    "command": command,
                    "user_role": self.user_role,
                    "session_id": self.session_id,
                    "timestamp": time.time(),
                },
            )

            # Check for risky commands (optional enhancement)
            risky_patterns = [
                "rm -r",
                "sudo rm",
                "dd if=",
                "mkfs",
                "fdisk",
                "chmod 777",
                "chown -R",
                "> /dev/",
            ]

            if any(pattern in command.lower() for pattern in risky_patterns):
                self.security_layer.audit_log(
                    action="risky_command_detected",
                    user=f"terminal_{self.session_id}",
                    outcome="warning",
                    details={
                        "command": command,
                        "risk_level": "high",
                        "user_role": self.user_role,
                    },
                )

        except Exception as e:
            logger.error(f"Security audit error: {e}")

    async def send_message(self, message: dict):
        """Send message to WebSocket client with standardized format"""
        if self.websocket and self.active:
            try:
                # Ensure standardized format
                standardized_message = message.copy()

                # Convert "data" field to "content" for consistency
                if "data" in standardized_message and "content" not in standardized_message:
                    standardized_message["content"] = standardized_message.pop("data")

                # Add metadata if not present
                if "metadata" not in standardized_message:
                    standardized_message["metadata"] = {
                        "session_id": self.session_id,
                        "timestamp": time.time(),
                        "terminal_type": "secure",
                        "user_role": self.user_role
                    }

                await self.websocket.send_text(json.dumps(standardized_message))
            except Exception as e:
                logger.error(f"WebSocket send error: {e}")

    async def disconnect(self):
        """Disconnect session and clean up PTY with security logging"""
        # Log session end before cleanup
        if self.security_layer:
            self.security_layer.audit_log(
                action="terminal_session_ended",
                user=f"terminal_{self.session_id}",
                outcome="disconnected",
                details={
                    "session_id": self.session_id,
                    "user_role": self.user_role,
                    "last_command": self.last_command,
                },
            )

        # Use base class cleanup method
        await self.cleanup()

        logger.info(f"Secure terminal session {self.session_id} disconnected")


# Global session manager
_secure_sessions: Dict[str, SecureTerminalSession] = {}


async def handle_secure_terminal_websocket(
    websocket: WebSocket, session_id: str, security_layer=None
):
    """Handle secure terminal WebSocket connection"""
    try:
        # Get user role from query parameters
        user_role = websocket.query_params.get("role", "user")

        # Create or get session
        if session_id not in _secure_sessions:
            session = SecureTerminalSession(
                session_id=session_id,
                security_layer=security_layer,
                user_role=user_role,
            )
            _secure_sessions[session_id] = session
        else:
            session = _secure_sessions[session_id]

        # Connect to session
        await session.connect(websocket)

        # Message processing loop
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                message_type = message.get("type", "")

                if message_type == "input":
                    # Send input to PTY - support multiple input field formats
                    text = message.get("content", message.get("text", message.get("data", "")))
                    if text:
                        await session.send_input(text)

                elif message_type == "ping":
                    # Respond to ping
                    await session.send_message({"type": "pong"})

                elif message_type == "resize":
                    # Handle terminal resize (could be implemented)
                    logger.info(f"Terminal resize request: {message}")

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                break
            except Exception as e:
                logger.error(f"Error in secure terminal loop: {e}")
                break

    finally:
        # Clean up session
        if session_id in _secure_sessions:
            await _secure_sessions[session_id].disconnect()
            del _secure_sessions[session_id]


def get_secure_session(session_id: str) -> Optional[SecureTerminalSession]:
    """Get a secure terminal session by ID"""
    return _secure_sessions.get(session_id)
