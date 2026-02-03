"""
Terminal WebSocket Handler for AutoBot
Handles bi-directional WebSocket communication for interactive terminal sessions
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.agents.system_command_agent import SystemCommandAgent
from src.event_manager import event_manager
from src.services.terminal_completion_service import TerminalCompletionService
from src.services.terminal_history_service import TerminalHistoryService

logger = logging.getLogger(__name__)

# Global instance of system command agent
system_command_agent = SystemCommandAgent()

# Terminal completion and history services
completion_service = TerminalCompletionService()
history_service = TerminalHistoryService()


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

    async def _handle_start_command(self, chat_id: str, data: Dict[str, Any]) -> None:
        """Handle start_command message. Issue #620."""
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

    async def _handle_input(self, chat_id: str, data: Dict[str, Any]) -> None:
        """Handle input message. Issue #620."""
        user_input = data.get("text", "")
        is_password = data.get("is_password", False)

        try:
            await system_command_agent.send_input_to_session(
                chat_id=chat_id, user_input=user_input, is_password=is_password
            )
            # Record command to history (Issue #749)
            if user_input.strip() and not is_password:
                asyncio.create_task(
                    history_service.add_command(chat_id, user_input.strip())
                )
        except ValueError as e:
            await self._send_error_to_chat(chat_id, str(e))

    async def _handle_control_action(self, chat_id: str, action: str) -> None:
        """Handle take_control or return_control messages. Issue #620."""
        try:
            if action == "take":
                await system_command_agent.take_control_of_session(chat_id)
            else:
                await system_command_agent.return_control_of_session(chat_id)
        except ValueError as e:
            await self._send_error_to_chat(chat_id, str(e))

    async def _handle_signal(self, chat_id: str, data: Dict[str, Any]) -> None:
        """Handle signal message. Issue #620."""
        signal_type = data.get("signal", "interrupt")
        try:
            await system_command_agent.send_signal_to_session(chat_id, signal_type)
        except ValueError as e:
            await self._send_error_to_chat(chat_id, str(e))

    async def _handle_resize(self, chat_id: str, data: Dict[str, Any]) -> None:
        """Handle resize message. Issue #620."""
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)

        session_id = f"{chat_id}_terminal"
        if session_id in system_command_agent.active_sessions:
            terminal = system_command_agent.active_sessions[session_id]
            await terminal.resize_terminal(cols, rows)

    async def _handle_get_sessions(self, chat_id: str) -> None:
        """Handle get_sessions message. Issue #620."""
        sessions = await system_command_agent.get_active_sessions()
        await self._send_message_to_chat(
            chat_id, {"type": "sessions", "sessions": sessions}
        )

    async def _handle_tab_completion(self, chat_id: str, data: Dict[str, Any]) -> None:
        """Handle tab_completion message. Issue #749."""
        text = data.get("text", "")
        cursor = data.get("cursor", len(text))
        cwd = data.get("cwd", os.path.expanduser("~"))
        if not os.path.isdir(cwd):
            cwd = os.path.expanduser("~")

        try:
            result = await completion_service.get_completions(text, cursor, cwd)
            await self._send_message_to_chat(
                chat_id,
                {
                    "type": "tab_completion",
                    "completions": result.completions,
                    "prefix": result.prefix,
                    "common_prefix": result.common_prefix,
                },
            )
        except Exception as e:
            logger.error("Tab completion error: %s", e)
            await self._send_message_to_chat(
                chat_id, {"type": "tab_completion", "completions": [], "error": str(e)}
            )

    async def _handle_history_get(self, chat_id: str, data: Dict[str, Any]) -> None:
        """Handle history_get message. Issue #749."""
        limit = min(max(1, data.get("limit", 100)), 1000)
        user_id = data.get("user_id", chat_id)  # Default to chat_id as user identifier

        try:
            commands = await history_service.get_history(user_id, limit=limit)
            await self._send_message_to_chat(
                chat_id, {"type": "history", "commands": commands}
            )
        except Exception as e:
            logger.error("History get error: %s", e)
            await self._send_message_to_chat(
                chat_id, {"type": "history", "commands": [], "error": str(e)}
            )

    async def _handle_history_search(self, chat_id: str, data: Dict[str, Any]) -> None:
        """Handle history_search message. Issue #749."""
        query = data.get("query", "")
        user_id = data.get("user_id", chat_id)
        limit = min(max(1, data.get("limit", 50)), 1000)

        try:
            matches = await history_service.search_history(user_id, query, limit=limit)
            await self._send_message_to_chat(
                chat_id, {"type": "history_search", "matches": matches, "query": query}
            )
        except Exception as e:
            logger.error("History search error: %s", e)
            await self._send_message_to_chat(
                chat_id, {"type": "history_search", "matches": [], "error": str(e)}
            )

    async def _process_client_message(self, chat_id: str, data: Dict[str, Any]):
        """
        Process messages from the client.

        Issue #620: Refactored to use extracted handler methods.
        """
        msg_type = data.get("type")

        if msg_type == "start_command":
            await self._handle_start_command(chat_id, data)
        elif msg_type == "input":
            await self._handle_input(chat_id, data)
        elif msg_type == "take_control":
            await self._handle_control_action(chat_id, "take")
        elif msg_type == "return_control":
            await self._handle_control_action(chat_id, "return")
        elif msg_type == "signal":
            await self._handle_signal(chat_id, data)
        elif msg_type == "resize":
            await self._handle_resize(chat_id, data)
        elif msg_type == "get_sessions":
            await self._handle_get_sessions(chat_id)
        elif msg_type == "tab_completion":
            await self._handle_tab_completion(chat_id, data)
        elif msg_type == "history_get":
            await self._handle_history_get(chat_id, data)
        elif msg_type == "history_search":
            await self._handle_history_search(chat_id, data)
        else:
            await self._send_error_to_chat(chat_id, f"Unknown message type: {msg_type}")

    def _build_event_message(
        self, event_type: str, event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build WebSocket message from event data. Issue #620.

        Args:
            event_type: Type of terminal event
            event_data: Raw event data from event manager

        Returns:
            Formatted message dictionary for WebSocket
        """
        if event_type == "terminal_output":
            return {
                "type": "output",
                "content": event_data.get("output", ""),
                "output_type": event_data.get("type", "output"),
                "timestamp": event_data.get("timestamp"),
            }
        elif event_type == "terminal_control":
            return {
                "type": "control_change",
                "status": event_data.get("status"),
                "message": event_data.get("message"),
            }
        elif event_type == "terminal_session":
            return {
                "type": "session_status",
                "status": event_data.get("status"),
                "exit_code": event_data.get("exit_code"),
                "duration": event_data.get("duration"),
            }
        elif event_type == "command_execution":
            return {
                "type": "command_status",
                "command": event_data.get("command"),
                "status": event_data.get("status"),
                "description": event_data.get("description"),
                "exit_code": event_data.get("exit_code"),
                "duration": event_data.get("duration"),
            }
        elif event_type == "command_confirmation":
            return {
                "type": "confirmation_request",
                "command": event_data.get("command"),
                "warning": event_data.get("warning"),
                "requires_confirmation": True,
            }
        return {"type": "unknown", "data": event_data}

    def _create_event_handler(
        self, chat_id: str, websocket: WebSocket, event_type: str
    ):
        """
        Create an event handler for a specific event type. Issue #620.

        Args:
            chat_id: Chat ID to filter events for
            websocket: WebSocket connection to send messages to
            event_type: Type of event to handle

        Returns:
            Async event handler function
        """

        async def handler(event_data):
            if event_data.get("chat_id") == chat_id:
                message = self._build_event_message(event_type, event_data)
                await self._send_message(websocket, message)

        return handler

    async def _subscribe_to_terminal_events(self, chat_id: str, websocket: WebSocket):
        """
        Subscribe to terminal events and forward to WebSocket.

        Issue #620: Refactored to use extracted helpers for handler creation.
        """
        # Issue #620: Event types to subscribe to
        event_types = [
            "terminal_output",
            "terminal_control",
            "terminal_session",
            "command_execution",
            "command_confirmation",
        ]

        # Create and register handlers
        handlers = {}
        for event_type in event_types:
            handler = self._create_event_handler(chat_id, websocket, event_type)
            handlers[event_type] = handler
            event_manager.subscribe(event_type, handler)

        # Keep the subscription alive
        try:
            while chat_id in self.active_connections:
                await asyncio.sleep(1)
        finally:
            # Unsubscribe all handlers
            for event_type, handler in handlers.items():
                event_manager.unsubscribe(event_type, handler)

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
