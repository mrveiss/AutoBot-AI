"""
Simplified Terminal WebSocket Handler for AutoBot
A working alternative to the complex PTY-based system
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

logger = logging.getLogger(__name__)


class SimpleTerminalSession:
    """Full-featured terminal session with PTY support for sudo commands"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.websocket: Optional[WebSocket] = None
        self.current_dir = "/home/kali"
        self.env = os.environ.copy()
        self.active = False
        self.pty_fd = None
        self.process = None
        self.reader_thread = None

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

    async def execute_command(self, command: str) -> bool:
        """Send command to PTY shell (now supports all commands including sudo)"""
        if not command.strip():
            return False

        logger.info(f"Sending to PTY: {command}")

        try:
            # Send command to PTY shell
            await self.send_input(command + "\n")
            return True

        except Exception as e:
            logger.error(f"PTY command error: {e}")
            await self.send_message(
                {"type": "error", "message": f"Terminal error: {str(e)}"}
            )
            return False

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
