"""
Simplified Terminal WebSocket Handler for AutoBot
A working alternative to the complex PTY-based system
"""

import asyncio
import json
import logging
import os
from typing import Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class SimpleTerminalSession:
    """Simple terminal session that actually works"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.websocket: Optional[WebSocket] = None
        self.current_dir = "/home/kali"
        self.env = os.environ.copy()
        self.active = False

    async def connect(self, websocket: WebSocket):
        """Connect WebSocket to this session"""
        await websocket.accept()
        self.websocket = websocket
        self.active = True

        # Send connection confirmation
        await self.send_message(
            {
                "type": "connection",
                "status": "connected",
                "message": "Simple terminal connected",
                "session_id": self.session_id,
                "working_dir": self.current_dir,
            }
        )

        # Send initial prompt
        await self.send_message(
            {"type": "output", "content": f"kali@autobot:{self.current_dir}$ "}
        )

        logger.info(f"Simple terminal session {self.session_id} connected")

    async def send_message(self, data: dict):
        """Send message to WebSocket"""
        if self.websocket:
            try:
                await self.websocket.send_text(json.dumps(data))
            except Exception as e:
                logger.error(f"Error sending message: {e}")

    async def execute_command(self, command: str) -> bool:
        """Execute a command and stream output"""
        if not command.strip():
            return False

        logger.info(f"Executing command: {command}")

        try:
            # Handle cd command specially
            if command.strip().startswith("cd "):
                path = command.strip()[3:].strip()
                if path == "":
                    path = os.path.expanduser("~")
                elif not os.path.isabs(path):
                    path = os.path.join(self.current_dir, path)

                if os.path.exists(path) and os.path.isdir(path):
                    self.current_dir = os.path.abspath(path)
                    await self.send_message(
                        {
                            "type": "output",
                            "content": f"kali@autobot:{self.current_dir}$ ",
                        }
                    )
                else:
                    await self.send_message(
                        {
                            "type": "output",
                            "content": f"cd: {path}: No such file or directory\n"
                            f"kali@autobot:{self.current_dir}$ ",
                        }
                    )
                return True

            # Execute other commands
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.current_dir,
                env=self.env,
            )

            # Stream output in real-time
            while True:
                output = await process.stdout.read(1024)
                if not output:
                    break

                # Send output to client
                await self.send_message(
                    {
                        "type": "output",
                        "content": output.decode("utf-8", errors="replace"),
                    }
                )

            # Wait for process to complete
            await process.wait()

            # Send new prompt
            await self.send_message(
                {"type": "output", "content": f"kali@autobot:{self.current_dir}$ "}
            )

            return True

        except Exception as e:
            logger.error(f"Command execution error: {e}")
            await self.send_message(
                {"type": "error", "message": f"Command failed: {str(e)}"}
            )
            await self.send_message(
                {"type": "output", "content": f"kali@autobot:{self.current_dir}$ "}
            )
            return False

    def disconnect(self):
        """Disconnect session"""
        self.active = False
        self.websocket = None
        logger.info(f"Simple terminal session {self.session_id} disconnected")


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
