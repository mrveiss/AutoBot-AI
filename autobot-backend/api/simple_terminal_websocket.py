"""
Simplified Terminal WebSocket Handler for AutoBot
A working alternative to the complex PTY-based system with enhanced security
"""

import json
import logging
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from .base_terminal import BaseTerminalWebSocket

# Import workflow automation for integration
try:
    from api.workflow_automation import workflow_manager

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

    # PTY shell startup now handled by base class

    async def send_message(self, data: dict):
        """Send message to WebSocket with standardized format"""
        if self.websocket:
            try:
                # Ensure standardized format - convert legacy field names
                standardized_data = data.copy()

                # Convert "data" field to "content" for consistency
                if "data" in standardized_data and "content" not in standardized_data:
                    standardized_data["content"] = standardized_data.pop("data")

                # Add metadata if not present
                if "metadata" not in standardized_data:
                    import time

                    standardized_data["metadata"] = {
                        "session_id": self.session_id,
                        "timestamp": time.time(),
                        "terminal_type": "simple",
                    }

                await self.websocket.send_text(json.dumps(standardized_data))
            except Exception as e:
                logger.error(f"Error sending message: {e}")

    # Input handling now in base class

    async def handle_workflow_control(self, data: Dict):
        """Handle workflow automation control messages"""
        if not WORKFLOW_AUTOMATION_AVAILABLE or not workflow_manager:
            await self.send_message(
                {"type": "error", "message": "Workflow automation not available"}
            )
            return

        try:
            action = data.get("action", "")
            workflow_id = data.get("workflow_id", "")

            logger.info(f"Handling workflow control: {action} for {workflow_id}")

            if action == "pause":
                # Pause any running automation
                await self.send_message(
                    {
                        "type": "workflow_paused",
                        "message": "🛑 Automation paused by user request",
                    }
                )

            elif action == "resume":
                # Resume automation
                await self.send_message(
                    {"type": "workflow_resumed", "message": "▶️ Automation resumed"}
                )

            elif action == "approve_step":
                step_id = data.get("step_id", "")
                await self.send_message(
                    {
                        "type": "workflow_step_approved",
                        "message": f"✅ Step {step_id} approved",
                        "step_id": step_id,
                    }
                )

            elif action == "cancel":
                await self.send_message(
                    {
                        "type": "workflow_cancelled",
                        "message": "❌ Workflow cancelled by user",
                    }
                )

            else:
                await self.send_message(
                    {"type": "error", "message": f"Unknown workflow action: {action}"}
                )

        except Exception as e:
            logger.error(f"Workflow control error: {e}")
            await self.send_message(
                {"type": "error", "message": f"Workflow message error: {str(e)}"}
            )

    async def disconnect(self):
        """Disconnect session and clean up PTY"""
        # Use base class cleanup method
        await self.cleanup()

        self.websocket = None
        logger.info(f"Full terminal session {self.session_id} disconnected")


class SimpleTerminalHandler:
    """Handler for simple terminal WebSocket connections"""

    def __init__(self):
        self.sessions: Dict[str, SimpleTerminalSession] = {}

    async def handle_websocket(self, websocket: WebSocket, session_id: str):
        """Handle simple terminal WebSocket connection"""
        try:
            # Create new session
            session = SimpleTerminalSession(session_id)
            self.sessions[session_id] = session

            # Connect to session
            await session.connect(websocket)

            # Message processing loop
            while True:
                try:
                    data = await websocket.receive_text()
                    message = json.loads(data)

                    message_type = message.get("type", "")

                    if message_type == "input":
                        # Send input to PTY shell - support both legacy and new formats
                        text = message.get(
                            "content", message.get("text", message.get("data", ""))
                        )
                        if text:
                            await session.send_input(text)

                    elif message_type == "workflow_control":
                        # Handle workflow automation controls
                        await session.handle_workflow_control(message)

                    elif message_type == "ping":
                        # Respond to ping for connection health
                        await session.send_message({"type": "pong"})

                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    break
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    break

        finally:
            await session.disconnect()
            if session_id in self.sessions:
                del self.sessions[session_id]

    def get_active_sessions(self) -> list:
        """Get list of active session IDs"""
        return list(self.sessions.keys())

    def get_session(self, session_id: str) -> SimpleTerminalSession:
        """Get session by ID"""
        return self.sessions.get(session_id)


# Global handler instance
simple_terminal_handler = SimpleTerminalHandler()


async def handle_simple_terminal_websocket(websocket: WebSocket, session_id: str):
    """Handle simple terminal WebSocket connection"""
    await simple_terminal_handler.handle_websocket(websocket, session_id)


def get_simple_terminal_sessions():
    """Get all active simple terminal sessions"""
    return simple_terminal_handler.get_active_sessions()


def get_simple_terminal_session(session_id: str):
    """Get a simple terminal session by ID"""
    return simple_terminal_handler.get_session(session_id)
