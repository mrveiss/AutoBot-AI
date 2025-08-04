"""
WebSocket API Router for AutoBot

This module handles WebSocket connections for real-time event streaming
between the backend and frontend clients.
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.event_manager import event_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event stream between backend and frontend.

    Handles:
    - Real-time event broadcasting from backend to frontend
    - Chat history integration for all events
    - Event type mapping and message formatting
    """
    await websocket.accept()
    logger.info(f"WebSocket connected from client: {websocket.client}")
    logger.info(f"Requested WebSocket path: {websocket.scope['path']}")
    logger.info(f"WebSocket connection type: {websocket.scope['type']}")

    # Access chat_history_manager from app.state via scope
    chat_history_manager = websocket.scope["app"].state.chat_history_manager

    async def broadcast_event(event_data: dict):
        """
        Broadcast event to WebSocket client and add to chat history.

        Args:
            event_data (dict): Event data containing type and payload
        """
        try:
            await websocket.send_json(event_data)

            # Add event to chat history manager
            sender = "system"
            text = ""
            message_type = event_data.get("type", "default")
            raw_data = event_data.get("payload", {})

            # Map event types to human-readable chat messages
            if message_type == "goal_received":
                text = f"Goal received: \"{raw_data.get('goal', 'N/A')}\""
            elif message_type == "plan_ready":
                text = f"Here is the plan:\n{raw_data.get('llm_response', 'No plan text available.')}"
                sender = "bot"
            elif message_type == "goal_completed":
                text = f"Goal completed. Result: {json.dumps(raw_data.get('results', {}), indent=2)}"
            elif message_type == "command_execution_start":
                text = f"Executing command: {raw_data.get('command', 'N/A')}"
            elif message_type == "command_execution_end":
                status = raw_data.get("status", "N/A")
                output = raw_data.get("output", "")
                error = raw_data.get("error", "")
                text = f"Command finished ({status}). Output: {output or error}"
            elif message_type == "error":
                text = f"Error: {raw_data.get('message', 'Unknown error')}"
                sender = "error"
            elif message_type == "progress":
                text = f"Progress: {raw_data.get('message', 'N/A')}"
            elif message_type == "llm_response":
                text = raw_data.get("response", "N/A")
                sender = "bot"
            elif message_type == "user_message":
                text = raw_data.get("message", "N/A")
                sender = "user"
            elif message_type == "thought":
                text = json.dumps(raw_data.get("thought", {}), indent=2)
                sender = "thought"
            elif message_type == "tool_code":
                text = raw_data.get("code", "N/A")
                sender = "tool-code"
            elif message_type == "tool_output":
                text = raw_data.get("output", "N/A")
                sender = "tool-output"
            elif message_type == "settings_updated":
                text = "Settings updated successfully."
            elif message_type == "file_uploaded":
                text = f"File uploaded: {raw_data.get('filename', 'N/A')}"
            elif message_type == "knowledge_base_update":
                text = f"Knowledge Base updated: {raw_data.get('type', 'N/A')}"
            elif message_type == "llm_status":
                status = raw_data.get("status", "N/A")
                model = raw_data.get("model", "N/A")
                message = raw_data.get("message", "")
                text = f"LLM ({model}) connection {status}. {message}"
                if status == "disconnected":
                    sender = "error"
            elif message_type == "diagnostics_report":
                text = f"Diagnostics Report: {json.dumps(raw_data, indent=2)}"
            elif message_type == "user_permission_request":
                text = f"User Permission Request: {json.dumps(raw_data, indent=2)}"

            # Add to chat history if we have meaningful text
            if text:
                chat_history_manager.add_message(sender, text, message_type, raw_data)

        except RuntimeError as e:
            logger.error(f"Error sending to WebSocket: {e}")
            # Connection may have been closed, continue silently

    # Register the broadcast function with the event manager
    event_manager.register_websocket_broadcast(broadcast_event)

    try:
        # Keep connection alive and handle incoming messages
        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                if data.get("type") == "user_message":
                    # Handle user messages if needed
                    # For now, just log them
                    logger.debug(f"Received user message via WebSocket: {data}")
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON via WebSocket: {message}")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Unregister the broadcast function when connection closes
        event_manager.register_websocket_broadcast(None)
        logger.info("WebSocket connection cleanup completed")
