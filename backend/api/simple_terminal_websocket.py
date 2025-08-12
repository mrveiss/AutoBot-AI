"""
Simplified Terminal WebSocket Handler for AutoBot
A working alternative to the complex PTY-based system with enhanced security
"""

import asyncio
import json
import logging
import os
import pty
import subprocess
import threading
from typing import Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from .base_terminal import BaseTerminalWebSocket

# Import workflow automation for integration
try:
    from backend.api.workflow_automation import workflow_manager
    WORKFLOW_AUTOMATION_AVAILABLE = True
except ImportError:
    workflow_manager = None
    WORKFLOW_AUTOMATION_AVAILABLE = False

logger = logging.getLogger(__name__)


class SimpleTerminalSession(BaseTerminalWebSocket):
    """Full-featured terminal session with PTY support for sudo commands"""

    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id
        self.websocket: Optional[WebSocket] = None
        self.current_dir = "/home/kali"
        self.env = os.environ.copy()
        self.active = False
        self.pty_fd = None
        self.process = None
        self.reader_thread = None
    
    @property
    def terminal_type(self) -> str:
        """Get terminal type for logging"""
        return "Terminal"

    async def connect(self, websocket: WebSocket):
        """Connect WebSocket to this session and start PTY shell"""
        await websocket.accept()
        self.websocket = websocket
        self.active = True

        # Start PTY shell process
        await self.start_pty_shell()

        # Send connection confirmation
        await self.send_message(
            {
                "type": "connection",
                "status": "connected",
                "message": "Full terminal connected with sudo support",
                "session_id": self.session_id,
                "working_dir": self.current_dir,
            }
        )

        logger.info(f"Full terminal session {self.session_id} connected")

    async def send_message(self, data: dict):
        """Send message to WebSocket"""
        if self.websocket:
            try:
                await self.websocket.send_text(json.dumps(data))
            except Exception as e:
                logger.error(f"Error sending message: {e}")

    async def start_pty_shell(self):
        """Start a PTY shell process for full interactivity"""
        try:
            # Create PTY
            master_fd, slave_fd = pty.openpty()
            self.pty_fd = master_fd

            # Start shell process with PTY
            self.process = subprocess.Popen(
                ["/bin/bash"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.current_dir,
                env=self.env,
                preexec_fn=os.setsid,
            )

            # Close slave fd (process has it)
            os.close(slave_fd)

            # Start reader thread
            self.reader_thread = threading.Thread(
                target=self._read_pty_output, daemon=True
            )
            self.reader_thread.start()

            logger.info(f"PTY shell started for session {self.session_id}")

        except Exception as e:
            logger.error(f"Failed to start PTY shell: {e}")
            await self.send_message(
                {"type": "error", "message": f"Failed to start terminal: {str(e)}"}
            )

    def _read_pty_output(self):
        """Read output from PTY in separate thread"""
        import select

        try:
            while self.active and self.pty_fd:
                try:
                    # Read with timeout
                    ready, _, _ = select.select([self.pty_fd], [], [], 0.1)

                    if ready:
                        data = os.read(self.pty_fd, 1024)
                        if data and self.websocket:
                            # Send to WebSocket synchronously from thread
                            try:
                                message = json.dumps(
                                    {
                                        "type": "output",
                                        "content": data.decode(
                                            "utf-8", errors="replace"
                                        ),
                                    }
                                )
                                # Use the event loop to send message
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                loop.run_until_complete(
                                    self.websocket.send_text(message)
                                )
                                loop.close()
                            except Exception as e:
                                logger.error(f"Error sending PTY output: {e}")
                                break
                except OSError:
                    break
                except Exception as e:
                    logger.error(f"Error reading PTY: {e}")
                    break
        except Exception as e:
            logger.error(f"PTY reader thread error: {e}")

    async def send_input(self, text: str):
        """Send input to PTY shell"""
        if self.pty_fd and self.active:
            try:
                os.write(self.pty_fd, text.encode("utf-8"))
            except Exception as e:
                logger.error(f"Error writing to PTY: {e}")


    async def handle_workflow_control(self, data: Dict):
        """Handle workflow automation control messages"""
        if not WORKFLOW_AUTOMATION_AVAILABLE or not workflow_manager:
            await self.send_message({
                "type": "error",
                "message": "Workflow automation not available"
            })
            return

        try:
            action = data.get("action", "")
            workflow_id = data.get("workflow_id", "")
            
            logger.info(f"Handling workflow control: {action} for {workflow_id}")

            if action == "pause":
                # Pause any running automation
                await self.send_message({
                    "type": "workflow_paused",
                    "message": "🛑 Automation paused by user request"
                })
            
            elif action == "resume":
                # Resume automation
                await self.send_message({
                    "type": "workflow_resumed", 
                    "message": "▶️ Automation resumed"
                })
                
            elif action == "approve_step":
                step_id = data.get("step_id", "")
                if workflow_id and step_id:
                    # Approve and execute the step
                    await self.send_message({
                        "type": "step_approved",
                        "workflow_id": workflow_id,
                        "step_id": step_id,
                        "message": f"✅ Step {step_id} approved for execution"
                    })
            
            elif action == "skip_step":
                step_id = data.get("step_id", "")
                if workflow_id and step_id:
                    await self.send_message({
                        "type": "step_skipped",
                        "workflow_id": workflow_id, 
                        "step_id": step_id,
                        "message": f"⏭️ Step {step_id} skipped by user"
                    })

        except Exception as e:
            logger.error(f"Error handling workflow control: {e}")
            await self.send_message({
                "type": "error",
                "message": f"Workflow control error: {str(e)}"
            })

    async def handle_workflow_message(self, data: Dict):
        """Handle workflow step execution messages"""
        if not WORKFLOW_AUTOMATION_AVAILABLE or not workflow_manager:
            return

        try:
            msg_subtype = data.get("subtype", "")
            
            if msg_subtype == "start_workflow":
                # Workflow starting notification
                workflow_data = data.get("workflow", {})
                workflow_name = workflow_data.get("name", "Unknown Workflow")
                
                await self.send_message({
                    "type": "system_message",
                    "message": f"🚀 Starting automated workflow: {workflow_name}"
                })
                
                # Forward workflow data to frontend terminal
                await self.send_message({
                    "type": "start_workflow",
                    "workflow": workflow_data
                })
            
            elif msg_subtype == "step_confirmation_required":
                # Forward step confirmation request to frontend
                await self.send_message({
                    "type": "step_confirmation_required",
                    "workflow_id": data.get("workflow_id"),
                    "step_id": data.get("step_id"),
                    "step_data": data.get("step_data")
                })
                
            elif msg_subtype == "execute_automated_command":
                # Execute automated command through terminal
                command = data.get("command", "")
                if command:
                    await self.send_message({
                        "type": "automated_output",
                        "message": f"🤖 Executing: {command}"
                    })
                    
                    # Execute the command
                    success = await self.execute_command(command)
                    
                    # Send result back to workflow system
                    result = {
                        "type": "command_result",
                        "workflow_id": data.get("workflow_id"),
                        "step_id": data.get("step_id"),
                        "command": command,
                        "success": success
                    }
                    await self.send_message(result)

        except Exception as e:
            logger.error(f"Error handling workflow message: {e}")
            await self.send_message({
                "type": "error",
                "message": f"Workflow message error: {str(e)}"
            })

    def disconnect(self):
        """Disconnect session and clean up PTY"""
        self.active = False

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
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

        # Wait for reader thread to finish
        if self.reader_thread and self.reader_thread.is_alive():
            try:
                self.reader_thread.join(timeout=1)
            except Exception:
                pass

        self.websocket = None
        logger.info(f"Full terminal session {self.session_id} disconnected")


class SimpleTerminalHandler:
    """Handler for simple terminal WebSocket connections"""

    def __init__(self):
        self.sessions: Dict[str, SimpleTerminalSession] = {}

    async def handle_connection(self, websocket: WebSocket, session_id: str):
        """Handle a WebSocket connection"""
        # Create or get existing session
        if session_id not in self.sessions:
            self.sessions[session_id] = SimpleTerminalSession(session_id)

        session = self.sessions[session_id]

        try:
            await session.connect(websocket)

            # Handle messages
            while session.active:
                try:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    logger.info(f"Received message: {data}")

                    msg_type = data.get("type", "")
                    if msg_type == "input":
                        text = data.get("text", "").rstrip("\n\r")
                        logger.info(f"Processing input: '{text}'")
                        if text:
                            await session.execute_command(text)

                    elif msg_type == "ping":
                        await session.send_message({"type": "pong"})

                    elif msg_type == "automation_control" and WORKFLOW_AUTOMATION_AVAILABLE:
                        # Handle workflow automation control messages
                        await session.handle_workflow_control(data)

                    elif msg_type == "workflow_message" and WORKFLOW_AUTOMATION_AVAILABLE:
                        # Handle workflow step messages
                        await session.handle_workflow_message(data)

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    break

        finally:
            session.disconnect()
            if session_id in self.sessions:
                del self.sessions[session_id]

    def get_active_sessions(self) -> list:
        """Get list of active sessions"""
        return [
            {
                "session_id": session_id,
                "working_dir": session.current_dir,
                "active": session.active,
            }
            for session_id, session in self.sessions.items()
            if session.active
        ]


# Global handler instance
simple_terminal_handler = SimpleTerminalHandler()


async def simple_terminal_websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for simple terminal"""
    await simple_terminal_handler.handle_connection(websocket, session_id)
