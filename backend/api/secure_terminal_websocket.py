"""
Secure Terminal WebSocket Handler with Command Auditing
Provides PTY terminal with enhanced security logging and optional sandboxing
"""

import asyncio
import json
import logging
import os
import pty
import subprocess
import threading
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
        self.websocket: Optional[WebSocket] = None
        self.current_dir = "/home/kali"
        self.env = os.environ.copy()
        self.active = False
        self.pty_fd = None
        self.process = None
        self.reader_thread = None
        
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
                    "logging_enabled": self.log_all_output
                }
            }
        )

    async def start_pty_shell(self):
        """Start a PTY shell process for full interactivity"""
        try:
            master_fd, slave_fd = pty.openpty()
            self.pty_fd = master_fd

            self.process = subprocess.Popen(
                ['/bin/bash'],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.current_dir,
                env=self.env,
                preexec_fn=os.setsid
            )

            os.close(slave_fd)  # Close slave_fd in parent process

            # Start reader thread
            self.reader_thread = threading.Thread(
                target=self._read_pty_output,
                daemon=True
            )
            self.reader_thread.start()

            logger.info(f"Secure PTY shell started for session {self.session_id}")

        except Exception as e:
            logger.error(f"Failed to start PTY shell: {e}")
            await self.send_message({
                "type": "error",
                "message": f"Failed to start secure terminal: {str(e)}"
            })

    def _read_pty_output(self):
        """Read output from PTY in separate thread and send via WebSocket"""
        try:
            while self.active and self.pty_fd:
                try:
                    # Read from PTY with timeout
                    import select
                    ready, _, _ = select.select([self.pty_fd], [], [], 0.1)
                    if ready:
                        data = os.read(self.pty_fd, 1024)
                        if data:
                            output = data.decode("utf-8", errors="ignore")
                            
                            # Log output if enabled
                            if self.log_all_output and self.security_layer:
                                self.security_layer.audit_log(
                                    action="terminal_output",
                                    user=f"terminal_{self.session_id}",
                                    outcome="logged",
                                    details={
                                        "output": output,
                                        "user_role": self.user_role
                                    }
                                )
                            
                            # Send to WebSocket
                            if self.websocket and self.active:
                                asyncio.run_coroutine_threadsafe(
                                    self.send_message({
                                        "type": "output",
                                        "data": output
                                    }),
                                    asyncio.get_event_loop()
                                )
                        else:
                            # PTY closed
                            break
                except OSError:
                    break
                except Exception as e:
                    logger.error(f"Error reading secure PTY: {e}")
                    break
        except Exception as e:
            logger.error(f"Secure PTY reader thread error: {e}")

    async def send_input(self, text: str):
        """Send input to PTY shell with command detection"""
        if self.pty_fd and self.active:
            try:
                # Track command input for auditing
                if "\n" in text or "\r" in text:
                    # Command completed
                    command = self.command_buffer + text.replace("\n", "").replace("\r", "")
                    if command.strip() and self.audit_commands:
                        await self.audit_command(command.strip())
                    self.command_buffer = ""
                else:
                    self.command_buffer += text
                
                os.write(self.pty_fd, text.encode("utf-8"))
            except Exception as e:
                logger.error(f"Error writing to secure PTY: {e}")

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
                    "working_dir": self.current_dir,
                    "timestamp": time.time()
                }
            )
            
            # Optionally assess command risk (for informational purposes)
            if hasattr(self.security_layer, 'command_executor'):
                risk, reasons = self.security_layer.command_executor.assess_command_risk(command)
                
                # Log risk assessment but don't block (since this is interactive terminal)
                if risk.value != "safe":
                    self.security_layer.audit_log(
                        action="terminal_command_risk_assessment",
                        user=f"terminal_{self.session_id}",
                        outcome="assessed",
                        details={
                            "command": command,
                            "risk_level": risk.value,
                            "reasons": reasons,
                            "action_taken": "none_terminal_session"
                        }
                    )
                    
                    # Optionally warn user about risky commands
                    if risk.value in ["high", "critical"]:
                        await self.send_message({
                            "type": "security_warning",
                            "message": f"⚠️  Security Notice: Command '{command}' is considered {risk.value} risk",
                            "risk": risk.value,
                            "reasons": reasons
                        })
                        
        except Exception as e:
            logger.error(f"Error auditing command: {e}")


    async def send_message(self, message: dict):
        """Send message to WebSocket client"""
        if self.websocket and self.active:
            try:
                await self.websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"WebSocket send error: {e}")

    def disconnect(self):
        """Disconnect session and clean up PTY"""
        self.active = False
        
        # Log session end
        if self.security_layer:
            self.security_layer.audit_log(
                action="terminal_session_ended",
                user=f"terminal_{self.session_id}",
                outcome="disconnected",
                details={
                    "session_id": self.session_id,
                    "user_role": self.user_role,
                    "last_command": self.last_command
                }
            )

        # Close PTY
        if self.pty_fd:
            try:
                os.close(self.pty_fd)
            except Exception:
                pass
            self.pty_fd = None

        # Terminate shell process
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
            self.process = None

        logger.info(f"Secure terminal session {self.session_id} disconnected")


# Global session manager
_secure_sessions: Dict[str, SecureTerminalSession] = {}


async def handle_secure_terminal_websocket(websocket: WebSocket, session_id: str, security_layer=None):
    """Handle secure terminal WebSocket connection"""
    global _secure_sessions
    
    try:
        # Get user role from query parameters
        user_role = websocket.query_params.get("role", "user")
        
        # Create or get session
        if session_id not in _secure_sessions:
            session = SecureTerminalSession(
                session_id=session_id,
                security_layer=security_layer,
                user_role=user_role
            )
            _secure_sessions[session_id] = session
        else:
            session = _secure_sessions[session_id]
            session.security_layer = security_layer  # Update security layer
            session.user_role = user_role

        await session.connect(websocket)

        # Handle WebSocket messages
        try:
            while session.active:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                    message = json.loads(data)

                    if message["type"] == "input":
                        await session.send_input(message["data"])
                    elif message["type"] == "command":
                        await session.execute_command(message["command"])
                    elif message["type"] == "resize":
                        # Handle terminal resize if needed
                        pass
                    elif message["type"] == "ping":
                        await session.send_message({"type": "pong"})

                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received from WebSocket")
                except Exception as e:
                    logger.error(f"WebSocket message handling error: {e}")

        except WebSocketDisconnect:
            logger.info(f"Secure WebSocket disconnected for session {session_id}")
        except Exception as e:
            logger.error(f"Secure WebSocket error: {e}")

    finally:
        # Clean up session
        if session_id in _secure_sessions:
            _secure_sessions[session_id].disconnect()
            del _secure_sessions[session_id]


def get_secure_session(session_id: str) -> Optional[SecureTerminalSession]:
    """Get active secure terminal session"""
    return _secure_sessions.get(session_id)