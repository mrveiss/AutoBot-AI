"""
Consolidated Terminal API - Merges all 4 terminal implementations
Provides unified REST API and WebSocket endpoints for terminal operations

Features consolidated from:
- terminal.py: Main REST API endpoints
- simple_terminal_websocket.py: Simple WebSocket + workflow control
- secure_terminal_websocket.py: Security auditing + command logging
- base_terminal.py: Infrastructure + PTY management
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
from src.constants.network_constants import NetworkConstants

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
    ):
        self.websocket = websocket
        self.session_id = session_id
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

        # Initialize PTY process if security level allows
        if security_level != SecurityLevel.RESTRICTED:
            self._init_pty_process()

    def _init_pty_process(self):
        """Initialize PTY process using SimplePTY"""
        try:
            from backend.services.simple_pty import simple_pty_manager

            # Create PTY session with SimplePTY manager
            self.pty_process = simple_pty_manager.create_session(
                self.session_id, initial_cwd="/home/kali/Desktop/AutoBot"
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

        # Start PTY output reader task if PTY is available
        if self.pty_process and self.pty_process.is_alive():
            self.pty_output_task = asyncio.create_task(self._read_pty_output())
            logger.info(f"PTY output reader started for session {self.session_id}")

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

        # Cancel output reader task if running
        if hasattr(self, "pty_output_task") and self.pty_output_task:
            try:
                self.pty_output_task.cancel()
                await asyncio.wait_for(self.pty_output_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.error(f"Error cancelling output task: {e}")

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
            elif message_type == "workflow_control":
                await self._handle_workflow_control(message)
            elif message_type == "ping":
                await self.send_message({"type": "pong", "timestamp": time.time()})
            elif message_type == "resize":
                await self._handle_resize(message)
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
        # Support both 'text' and 'content' fields for compatibility
        text = message.get("text") or message.get("content", "")

        if not text:
            return

        # Security assessment for commands
        risk_level = self._assess_command_risk(text)

        # Log command for audit trail
        if self.enable_logging:
            self._log_command_activity(
                "command_input",
                {
                    "command": text,
                    "risk_level": risk_level.value,
                    "user_role": self.user_role,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Add to command history
        self.command_history.append(
            {
                "command": text,
                "timestamp": datetime.now(),
                "risk_level": risk_level.value,
            }
        )

        # Apply security restrictions
        if await self._should_block_command(text, risk_level):
            await self.send_message(
                {
                    "type": "security_warning",
                    "content": f"Command blocked due to {risk_level.value} "
                    f"risk level: {text}",
                    "risk_level": risk_level.value,
                    "timestamp": time.time(),
                }
            )
            return

        # Send to terminal
        await self.send_to_terminal(text)

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
        """Enhanced output sending with standardized format"""
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

        await self.send_message(message)

        # Log output if security logging enabled
        if self.enable_logging and len(content.strip()) > 0:
            self._log_command_activity(
                "command_output",
                {
                    "output_length": len(content),
                    "timestamp": datetime.now().isoformat(),
                },
            )


# Enhanced session manager for consolidated terminal
class ConsolidatedTerminalManager:
    """Enhanced session manager for consolidated terminal API"""

    def __init__(self):
        self.session_configs = {}  # session_id -> config
        self.active_connections = {}  # session_id -> ConsolidatedTerminalWebSocket
        self.session_stats = {}  # session_id -> statistics

    def add_connection(self, session_id: str, terminal: ConsolidatedTerminalWebSocket):
        """Add a WebSocket connection for a session"""
        self.active_connections[session_id] = terminal
        self.session_stats[session_id] = {
            "connected_at": datetime.now(),
            "messages_sent": 0,
            "messages_received": 0,
            "commands_executed": 0,
        }

    def remove_connection(self, session_id: str):
        """Remove a WebSocket connection"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        # Keep stats for audit purposes

    def has_connection(self, session_id: str) -> bool:
        """Check if session has active connection"""
        return session_id in self.active_connections

    async def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a session"""
        if session_id in self.active_connections:
            terminal = self.active_connections[session_id]
            await terminal.send_to_terminal(text)
            self.session_stats[session_id]["commands_executed"] += 1
            return True
        return False

    async def send_signal(self, session_id: str, sig: int) -> bool:
        """Send signal to a session"""
        if session_id in self.active_connections:
            # Implementation would depend on PTY process handling
            return True
        return False

    async def close_connection(self, session_id: str):
        """Close a session connection"""
        if session_id in self.active_connections:
            terminal = self.active_connections[session_id]
            await terminal.cleanup()
            self.remove_connection(session_id)

    def get_session_stats(self, session_id: str) -> dict:
        """Get statistics for a session"""
        return self.session_stats.get(session_id, {})

    def get_command_history(self, session_id: str) -> list:
        """Get command history for a session"""
        if session_id in self.active_connections:
            terminal = self.active_connections[session_id]
            return [
                {
                    "command": entry["command"],
                    "timestamp": entry["timestamp"].isoformat(),
                    "risk_level": entry["risk_level"],
                }
                for entry in terminal.command_history
            ]
        return []


# Global session manager
session_manager = ConsolidatedTerminalManager()

# REST API Endpoints


@router.post("/sessions")
async def create_terminal_session(request: TerminalSessionRequest):
    """Create a new terminal session with enhanced security options"""
    try:
        session_id = str(uuid.uuid4())

        # Store session configuration for WebSocket connection
        session_config = {
            "session_id": session_id,
            "user_id": request.user_id,
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

    except Exception as e:
        logger.error(f"Error creating terminal session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_terminal_sessions():
    """List all active terminal sessions"""
    try:
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

    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_terminal_session(session_id: str):
    """Get information about a specific terminal session"""
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_terminal_session(session_id: str):
    """Delete a terminal session and close any active connections"""
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/command")
async def execute_single_command(request: CommandRequest):
    """Execute a single command with security assessment"""
    try:
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

    except Exception as e:
        logger.error(f"Error executing command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/input")
async def send_terminal_input(session_id: str, request: TerminalInputRequest):
    """Send input to a specific terminal session"""
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending input to session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/signal/{signal_name}")
async def send_terminal_signal(session_id: str, signal_name: str):
    """Send a signal to a terminal session"""
    try:
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
            raise HTTPException(
                status_code=400, detail=f"Invalid signal: {signal_name}"
            )

        success = await session_manager.send_signal(session_id, signal_map[signal_name])

        if success:
            return {"session_id": session_id, "signal": signal_name, "status": "sent"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send signal")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending signal to session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/history")
async def get_terminal_command_history(session_id: str):
    """Get command history for a terminal session"""
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting command history for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/{session_id}")
async def get_session_audit_log(session_id: str):
    """Get security audit log for a session (elevated access required)"""
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit log for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket Endpoints


@router.websocket("/ws/{session_id}")
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

        # Create consolidated terminal handler
        terminal = ConsolidatedTerminalWebSocket(websocket, session_id, security_level)

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


@router.post("/terminal/install-tool")
async def install_tool(request: ToolInstallRequest):
    """Install a tool with terminal streaming"""
    try:
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

    except Exception as e:
        logger.error(f"Error installing tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/check-tool")
async def check_tool_installed(tool_name: str):
    """Check if a tool is installed"""
    try:
        from src.agents.system_command_agent import SystemCommandAgent

        system_command_agent = SystemCommandAgent()
        result = await system_command_agent.check_tool_installed(tool_name)
        return result

    except Exception as e:
        logger.error(f"Error checking tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/validate-command")
async def validate_command(command: str):
    """Validate command safety"""
    try:
        from src.agents.system_command_agent import SystemCommandAgent

        system_command_agent = SystemCommandAgent()
        result = await system_command_agent.validate_command_safety(command)
        return result

    except Exception as e:
        logger.error(f"Error validating command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/terminal/package-managers")
async def get_package_managers():
    """Get available package managers"""
    try:
        from src.agents.system_command_agent import SystemCommandAgent

        system_command_agent = SystemCommandAgent()
        detected = await system_command_agent.detect_package_manager()
        all_managers = list(system_command_agent.PACKAGE_MANAGERS.keys())

        return {
            "detected": detected,
            "available": all_managers,
            "package_managers": system_command_agent.PACKAGE_MANAGERS,
        }

    except Exception as e:
        logger.error(f"Error getting package managers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Information endpoints


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
