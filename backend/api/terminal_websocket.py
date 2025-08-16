"""
Terminal WebSocket Handler for AutoBot
Handles bi-directional WebSocket communication for interactive terminal sessions
"""

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.agents.system_command_agent import SystemCommandAgent
from src.event_manager import event_manager

logger = logging.getLogger(__name__)

# Global instance of system command agent
system_command_agent = SystemCommandAgent()


class TerminalWebSocketHandler:
    """Handles bi-directional WebSocket communication for terminal sessions"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.event_subscriptions: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, chat_id: str):
        """Accept WebSocket connection and setup event listeners"""
        await websocket.accept()
        self.active_connections[chat_id] = websocket

        # Subscribe to terminal events for this chat
        event_task = asyncio.create_task(
            self._subscribe_to_terminal_events(chat_id, websocket)
        )
        self.event_subscriptions[chat_id] = event_task

        logger.info(f"Terminal WebSocket connected for chat {chat_id}")

        # Initialize terminal session for this chat if it doesn't exist
        try:
            # Start an interactive bash shell for this chat session
            # Try the full path first
            logger.info(f"Attempting to initialize terminal session for chat {chat_id}")
            await system_command_agent.execute_interactive_command(
                command="/bin/bash -i",
                chat_id=chat_id,
                description="Initialize interactive terminal session",
                require_confirmation=False,
            )
            logger.info(f"Successfully initialized terminal session for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to initialize terminal session for {chat_id}: {e}")
            # Send error message to client
            await self._send_message(
                websocket,
                {
                    "type": "error",
                    "message": f"Failed to initialize terminal session: {str(e)}",
                    "details": str(e),
                },
            )

        # Send initial connection success message
        await self._send_message(
            websocket,
            {
                "type": "connection",
                "status": "connected",
                "message": "Terminal WebSocket connected successfully",
            },
        )

    async def disconnect(self, chat_id: str):
        """Clean up WebSocket connection"""
        # Cancel event subscription
        if chat_id in self.event_subscriptions:
            self.event_subscriptions[chat_id].cancel()
            del self.event_subscriptions[chat_id]

        # Remove from active connections
        if chat_id in self.active_connections:
            del self.active_connections[chat_id]

        logger.info(f"Terminal WebSocket disconnected for chat {chat_id}")

    async def handle_terminal_session(self, websocket: WebSocket, chat_id: str):
        """Main WebSocket handler for terminal sessions"""
        try:
            await self.connect(websocket, chat_id)

            while websocket.client_state == WebSocketState.CONNECTED:
                # Receive message from client with timeout
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await websocket.send_text(json.dumps({"type": "ping"}))
                    continue
                except Exception:
                    break

                try:
                    data = json.loads(message)
                    # Process different message types
                    await self._process_client_message(chat_id, data)

                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError as e:
                    await self._send_error(websocket, f"Invalid JSON: {str(e)}")
                except Exception as e:
                    logger.error(f"Error handling WebSocket message: {e}")
                    await self._send_error(
                        websocket, f"Error processing message: {str(e)}"
                    )

        except Exception as e:
            logger.error(f"WebSocket session error: {e}")
        finally:
            await self.disconnect(chat_id)

    async def _process_client_message(self, chat_id: str, data: Dict[str, Any]):
        """Process messages from the client"""
        msg_type = data.get("type")

        if msg_type == "start_command":
            # Start a new command
            command = data.get("command", "")
            description = data.get("description", "")
            require_confirmation = data.get("require_confirmation", True)

            asyncio.create_task(
                system_command_agent.execute_interactive_command(
                    command=command,
                    chat_id=chat_id,
                    description=description,
                    require_confirmation=require_confirmation,
                )
            )

        elif msg_type == "input":
            # Send input to terminal
            user_input = data.get("text", "")
            is_password = data.get("is_password", False)

            try:
                await system_command_agent.send_input_to_session(
                    chat_id=chat_id, user_input=user_input, is_password=is_password
                )
            except ValueError as e:
                await self._send_error_to_chat(chat_id, str(e))

        elif msg_type == "take_control":
            # User wants to take control
            try:
                await system_command_agent.take_control_of_session(chat_id)
            except ValueError as e:
                await self._send_error_to_chat(chat_id, str(e))

        elif msg_type == "return_control":
            # Return control to agent
            try:
                await system_command_agent.return_control_of_session(chat_id)
            except ValueError as e:
                await self._send_error_to_chat(chat_id, str(e))

        elif msg_type == "signal":
            # Send signal to process
            signal_type = data.get("signal", "interrupt")
            try:
                await system_command_agent.send_signal_to_session(chat_id, signal_type)
            except ValueError as e:
                await self._send_error_to_chat(chat_id, str(e))

        elif msg_type == "resize":
            # Resize terminal
            cols = data.get("cols", 80)
            rows = data.get("rows", 24)

            session_id = f"{chat_id}_terminal"
            if session_id in system_command_agent.active_sessions:
                terminal = system_command_agent.active_sessions[session_id]
                await terminal.resize_terminal(cols, rows)

        elif msg_type == "get_sessions":
            # Get active sessions
            sessions = await system_command_agent.get_active_sessions()
            await self._send_message_to_chat(
                chat_id, {"type": "sessions", "sessions": sessions}
            )

        else:
            await self._send_error_to_chat(chat_id, f"Unknown message type: {msg_type}")

    async def _subscribe_to_terminal_events(self, chat_id: str, websocket: WebSocket):
        """Subscribe to terminal events and forward to WebSocket"""

        async def handle_terminal_output(event_data):
            if event_data.get("chat_id") == chat_id:
                await self._send_message(
                    websocket,
                    {
                        "type": "output",
                        "content": event_data.get("output", ""),
                        "output_type": event_data.get("type", "output"),
                        "timestamp": event_data.get("timestamp"),
                    },
                )

        async def handle_terminal_control(event_data):
            if event_data.get("chat_id") == chat_id:
                await self._send_message(
                    websocket,
                    {
                        "type": "control_change",
                        "status": event_data.get("status"),
                        "message": event_data.get("message"),
                    },
                )

        async def handle_terminal_session(event_data):
            if event_data.get("chat_id") == chat_id:
                await self._send_message(
                    websocket,
                    {
                        "type": "session_status",
                        "status": event_data.get("status"),
                        "exit_code": event_data.get("exit_code"),
                        "duration": event_data.get("duration"),
                    },
                )

        async def handle_command_execution(event_data):
            if event_data.get("chat_id") == chat_id:
                await self._send_message(
                    websocket,
                    {
                        "type": "command_status",
                        "command": event_data.get("command"),
                        "status": event_data.get("status"),
                        "description": event_data.get("description"),
                        "exit_code": event_data.get("exit_code"),
                        "duration": event_data.get("duration"),
                    },
                )

        async def handle_command_confirmation(event_data):
            if event_data.get("chat_id") == chat_id:
                await self._send_message(
                    websocket,
                    {
                        "type": "confirmation_request",
                        "command": event_data.get("command"),
                        "warning": event_data.get("warning"),
                        "requires_confirmation": True,
                    },
                )

        # Subscribe to events
        event_manager.subscribe("terminal_output", handle_terminal_output)
        event_manager.subscribe("terminal_control", handle_terminal_control)
        event_manager.subscribe("terminal_session", handle_terminal_session)
        event_manager.subscribe("command_execution", handle_command_execution)
        event_manager.subscribe("command_confirmation", handle_command_confirmation)

        # Keep the subscription alive
        try:
            while chat_id in self.active_connections:
                await asyncio.sleep(1)
        finally:
            # Unsubscribe when done
            event_manager.unsubscribe("terminal_output", handle_terminal_output)
            event_manager.unsubscribe("terminal_control", handle_terminal_control)
            event_manager.unsubscribe("terminal_session", handle_terminal_session)
            event_manager.unsubscribe("command_execution", handle_command_execution)
            event_manager.unsubscribe(
                "command_confirmation", handle_command_confirmation
            )

    async def _send_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to WebSocket if connection is open"""
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")

    async def _send_message_to_chat(self, chat_id: str, message: Dict[str, Any]):
        """Send message to specific chat WebSocket"""
        if chat_id in self.active_connections:
            await self._send_message(self.active_connections[chat_id], message)

    async def _send_error(self, websocket: WebSocket, error: str):
        """Send error message to WebSocket"""
        await self._send_message(websocket, {"type": "error", "error": error})

    async def _send_error_to_chat(self, chat_id: str, error: str):
        """Send error message to specific chat"""
        await self._send_message_to_chat(chat_id, {"type": "error", "error": error})


# Create global instance
terminal_ws_handler = TerminalWebSocketHandler()


# FastAPI WebSocket endpoint
async def terminal_websocket_endpoint(websocket: WebSocket, chat_id: str):
    """FastAPI endpoint for terminal WebSocket connections"""
    await terminal_ws_handler.handle_terminal_session(websocket, chat_id)
