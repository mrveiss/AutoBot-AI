# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Desktop Streaming Manager for AutoBot Phase 8
Provides NoVNC integration and WebSocket-based desktop streaming capabilities
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import websockets

from src.constants.network_constants import NetworkConstants
from src.task_execution_tracker import task_tracker
from src.unified_config_manager import config_manager

logger = logging.getLogger(__name__)


class VNCServerManager:
    """Manages VNC server instances for desktop streaming"""

    def __init__(
        self, display_base: int = 10, port_base: int = 5900, novnc_port_base: int = 6080
    ):
        self.display_base = display_base
        self.port_base = port_base
        self.novnc_port_base = novnc_port_base
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

        # Check for VNC server availability
        self.vnc_available = self._check_vnc_availability()
        self.novnc_available = self._check_novnc_availability()

        logger.info(
            f"VNC Server Manager initialized: VNC={self.vnc_available}, NoVNC={self.novnc_available}"
        )

    def _check_vnc_availability(self) -> bool:
        """Check if VNC server components are available"""
        try:
            # Check for tigervnc or tightvnc
            result = subprocess.run(
                ["which", "vncserver"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return True

            # Check for Xvfb (alternative)
            result = subprocess.run(["which", "Xvfb"], capture_output=True, text=True)
            return result.returncode == 0

        except Exception as e:
            logger.warning(f"VNC availability check failed: {e}")
            return False

    def _check_novnc_availability(self) -> bool:
        """Check if NoVNC components are available"""
        # Common NoVNC installation paths
        novnc_paths = ["/usr/share/novnc", "/opt/novnc", "~/novnc", "./novnc"]

        for path in novnc_paths:
            if Path(path).expanduser().exists():
                return True

        return False

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        resolution: str = "1024x768",
        depth: int = 24,
    ) -> Dict[str, Any]:
        """Create a new VNC session for desktop streaming"""

        async with task_tracker.track_task(
            "Create VNC Session",
            f"Creating desktop streaming session for user {user_id}",
            agent_type="desktop_streaming",
            priority=TaskPriority.HIGH,
            inputs={
                "session_id": session_id,
                "user_id": user_id,
                "resolution": resolution,
            },
        ) as task_context:
            if not self.vnc_available:
                error_msg = "VNC server not available on system"
                task_context.set_outputs({"error": error_msg})
                raise RuntimeError(error_msg)

            # Find available display and port
            display_num = self._find_available_display()
            vnc_port = self.port_base + display_num
            novnc_port = self.novnc_port_base + display_num

            try:
                # Start Xvfb virtual display
                xvfb_command = [
                    "Xvfb",
                    f":{display_num}",
                    "-screen",
                    "0",
                    f"{resolution}x{depth}",
                    "-nolisten",
                    "tcp",
                    "-dpi",
                    "96",
                ]

                xvfb_process = subprocess.Popen(
                    xvfb_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )

                # Wait for display to be ready
                await asyncio.sleep(2)

                # Start VNC server
                vnc_command = [
                    "x11vnc",
                    "-display",
                    f":{display_num}",
                    "-rfbport",
                    str(vnc_port),
                    "-shared",
                    "-forever",
                    "-noxdamage",
                    "-noxfixes",
                    "-noxcomposite",
                ]

                vnc_process = subprocess.Popen(
                    vnc_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )

                # Start NoVNC if available
                novnc_process = None
                if self.novnc_available:
                    novnc_process = await self._start_novnc(vnc_port, novnc_port)

                # Create session record
                session_data = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "display_num": display_num,
                    "vnc_port": vnc_port,
                    "novnc_port": novnc_port,
                    "resolution": resolution,
                    "depth": depth,
                    "created_at": time.time(),
                    "xvfb_process": xvfb_process,
                    "vnc_process": vnc_process,
                    "novnc_process": novnc_process,
                    "status": "active",
                }

                self.active_sessions[session_id] = session_data

                # Set task outputs
                outputs = {
                    "session_id": session_id,
                    "vnc_port": vnc_port,
                    "novnc_port": novnc_port if self.novnc_available else None,
                    "display": f":{display_num}",
                    "vnc_url": f"vnc://localhost:{vnc_port}",
                    "web_url": (
                        f"http://localhost:{novnc_port}"
                        if self.novnc_available
                        else None
                    ),
                }

                task_context.set_outputs(outputs)

                logger.info(
                    f"VNC session created: {session_id} on display :{display_num}"
                )
                return outputs

            except Exception as e:
                error_msg = f"Failed to create VNC session: {str(e)}"
                task_context.set_outputs({"error": error_msg})
                raise RuntimeError(error_msg)

    async def _start_novnc(
        self, vnc_port: int, novnc_port: int
    ) -> Optional[subprocess.Popen]:
        """Start NoVNC web proxy"""
        try:
            # Try to find websockify
            websockify_paths = [
                "/usr/bin/websockify",
                "/usr/local/bin/websockify",
                "~/.local/bin/websockify",
            ]

            websockify_cmd = None
            for path in websockify_paths:
                if Path(path).expanduser().exists():
                    websockify_cmd = str(Path(path).expanduser())
                    break

            if not websockify_cmd:
                logger.warning("Websockify not found, NoVNC will not be available")
                return None

            # Start websockify
            novnc_command = [
                websockify_cmd,
                "--web",
                "/usr/share/novnc",
                str(novnc_port),
                f"localhost:{vnc_port}",
            ]

            novnc_process = subprocess.Popen(
                novnc_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            logger.info(f"NoVNC started on port {novnc_port}")
            return novnc_process

        except Exception as e:
            logger.error(f"Failed to start NoVNC: {e}")
            return None

    def _find_available_display(self) -> int:
        """Find an available X display number"""
        for i in range(self.display_base, self.display_base + 100):
            lock_file = Path(f"/tmp/.X{i}-lock")
            if not lock_file.exists():
                return i

        raise RuntimeError("No available X display numbers")

    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a VNC session"""
        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]

        try:
            # Terminate processes
            for process_key in ["novnc_process", "vnc_process", "xvfb_process"]:
                process = session.get(process_key)
                if process:
                    try:
                        process.terminate()
                        # Wait for graceful termination
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    except Exception as e:
                        logger.warning(f"Error terminating {process_key}: {e}")

            # Remove session
            del self.active_sessions[session_id]

            logger.info(f"VNC session terminated: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error terminating session {session_id}: {e}")
            return False

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a VNC session"""
        if session_id not in self.active_sessions:
            return None

        session = self.active_sessions[session_id].copy()
        # Remove process objects from returned data
        for key in ["xvfb_process", "vnc_process", "novnc_process"]:
            session.pop(key, None)

        return session

    def list_active_sessions(self) -> List[Dict[str, Any]]:
        """List all active VNC sessions"""
        sessions = []
        for session_id, session_data in self.active_sessions.items():
            session_info = self.get_session_info(session_id)
            if session_info:
                sessions.append(session_info)

        return sessions

    async def cleanup_stale_sessions(self) -> int:
        """Clean up stale or orphaned sessions"""
        cleanup_count = 0
        stale_sessions = []

        for session_id, session_data in self.active_sessions.items():
            # Check if processes are still running
            processes_alive = 0
            for process_key in ["xvfb_process", "vnc_process"]:
                process = session_data.get(process_key)
                if process and process.poll() is None:
                    processes_alive += 1

            # If no core processes are alive, mark as stale
            if processes_alive == 0:
                stale_sessions.append(session_id)

        # Cleanup stale sessions
        for session_id in stale_sessions:
            await self.terminate_session(session_id)
            cleanup_count += 1

        if cleanup_count > 0:
            logger.info(f"Cleaned up {cleanup_count} stale VNC sessions")

        return cleanup_count


class DesktopStreamingManager:
    """High-level desktop streaming manager with WebSocket integration"""

    def __init__(self):
        self.vnc_manager = VNCServerManager()
        self.websocket_clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.session_clients: Dict[str, List[str]] = (
            {}
        )  # session_id -> list of client_ids

        logger.info("Desktop Streaming Manager initialized")

    async def create_streaming_session(
        self, user_id: str, session_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new desktop streaming session"""
        config = session_config or {}
        session_id = f"stream_{user_id}_{int(time.time())}"

        # Create VNC session
        vnc_info = await self.vnc_manager.create_session(
            session_id=session_id,
            user_id=user_id,
            resolution=config.get("resolution", "1024x768"),
            depth=config.get("depth", 24),
        )

        # Initialize client tracking
        self.session_clients[session_id] = []

        return {
            **vnc_info,
            "streaming_available": True,
            "websocket_endpoint": f"/ws/desktop/{session_id}",
        }

    async def handle_websocket_client(self, websocket, path: str):
        """Handle WebSocket connections for desktop streaming"""
        try:
            # Extract session ID from path
            path_parts = path.strip("/").split("/")
            if len(path_parts) >= 3 and path_parts[1] == "desktop":
                session_id = path_parts[2]
            else:
                await websocket.close(code=1008, reason="Invalid path")
                return

            # Verify session exists
            if session_id not in self.session_clients:
                await websocket.close(code=1008, reason="Session not found")
                return

            client_id = f"client_{id(websocket)}"
            self.websocket_clients[client_id] = websocket
            self.session_clients[session_id].append(client_id)

            logger.info(
                f"WebSocket client connected: {client_id} to session {session_id}"
            )

            # Send initial session info
            session_info = self.vnc_manager.get_session_info(session_id)
            if session_info:
                await websocket.send(
                    json.dumps({"type": "session_info", "data": session_info})
                )

            # Handle client messages
            async for message in websocket:
                await self._handle_client_message(client_id, session_id, message)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            # Cleanup
            if client_id in self.websocket_clients:
                del self.websocket_clients[client_id]
            if (
                session_id in self.session_clients
                and client_id in self.session_clients[session_id]
            ):
                self.session_clients[session_id].remove(client_id)

    async def _handle_client_message(
        self, client_id: str, session_id: str, message: str
    ):
        """Handle messages from WebSocket clients"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "control_request":
                # Handle control requests (mouse, keyboard, etc.)
                await self._handle_control_request(session_id, data.get("data", {}))

            elif msg_type == "get_screenshot":
                # Handle screenshot requests
                screenshot_data = await self._get_session_screenshot(session_id)
                if screenshot_data:
                    await self.websocket_clients[client_id].send(
                        json.dumps({"type": "screenshot", "data": screenshot_data})
                    )

            elif msg_type == "session_status":
                # Handle status requests
                status = self.vnc_manager.get_session_info(session_id)
                await self.websocket_clients[client_id].send(
                    json.dumps({"type": "session_status", "data": status})
                )

        except Exception as e:
            logger.error(f"Error handling client message: {e}")

    async def _handle_control_request(
        self, session_id: str, control_data: Dict[str, Any]
    ):
        """Handle desktop control requests"""
        session_info = self.vnc_manager.get_session_info(session_id)
        if not session_info:
            return

        display = session_info["display_num"]

        try:
            control_type = control_data.get("type")

            if control_type == "mouse_click":
                x, y = control_data.get("x", 0), control_data.get("y", 0)
                button = control_data.get("button", 1)

                # Use xdotool to simulate mouse click
                subprocess.run(
                    [
                        "xdotool",
                        "mousemove",
                        "--sync",
                        str(x),
                        str(y),
                        "click",
                        str(button),
                    ],
                    env={
                        **config_manager.get("system.environment", os.environ),
                        "DISPLAY": f":{display}",
                    },
                )

            elif control_type == "key_press":
                key = control_data.get("key", "")
                if key:
                    subprocess.run(
                        ["xdotool", "key", key],
                        env={
                            **config_manager.get("system.environment", os.environ),
                            "DISPLAY": f":{display}",
                        },
                    )

            elif control_type == "type_text":
                text = control_data.get("text", "")
                if text:
                    subprocess.run(
                        ["xdotool", "type", text],
                        env={
                            **config_manager.get("system.environment", os.environ),
                            "DISPLAY": f":{display}",
                        },
                    )

        except Exception as e:
            logger.error(f"Control request failed: {e}")

    async def _get_session_screenshot(self, session_id: str) -> Optional[str]:
        """Get screenshot from desktop session"""
        session_info = self.vnc_manager.get_session_info(session_id)
        if not session_info:
            return None

        try:
            display = session_info["display_num"]

            # Use imagemagick to capture screenshot
            result = subprocess.run(
                ["import", "-window", "root", "-display", f":{display}", "png:-"],
                capture_output=True,
            )

            if result.returncode == 0:
                # Return base64 encoded PNG
                import base64

                return base64.b64encode(result.stdout).decode("utf-8")

        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")

        return None

    async def terminate_streaming_session(self, session_id: str) -> bool:
        """Terminate a desktop streaming session"""
        # Notify all connected clients
        if session_id in self.session_clients:
            for client_id in self.session_clients[session_id].copy():
                if client_id in self.websocket_clients:
                    try:
                        await self.websocket_clients[client_id].send(
                            json.dumps(
                                {
                                    "type": "session_terminated",
                                    "data": {"session_id": session_id},
                                }
                            )
                        )
                        await self.websocket_clients[client_id].close()
                    except Exception as e:
                        logger.warning(f"Error notifying client {client_id}: {e}")

            del self.session_clients[session_id]

        # Terminate VNC session
        return await self.vnc_manager.terminate_session(session_id)

    def get_system_capabilities(self) -> Dict[str, Any]:
        """Get desktop streaming system capabilities"""
        return {
            "vnc_available": self.vnc_manager.vnc_available,
            "novnc_available": self.vnc_manager.novnc_available,
            "active_sessions": len(self.vnc_manager.active_sessions),
            "connected_clients": len(self.websocket_clients),
            "max_concurrent_sessions": 10,  # Configurable limit
            "supported_features": [
                "screen_sharing",
                "remote_control",
                "screenshot_capture",
                "websocket_streaming",
            ],
        }


# Global instance
desktop_streaming = DesktopStreamingManager()
