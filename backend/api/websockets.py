"""
WebSocket API Router for AutoBot

This module handles WebSocket connections for real-time event streaming
between the backend and frontend clients.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

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
            metadata = event_data.get("payload", {})

            # Map event types to human-readable chat messages
            if message_type == "goal_received":
                text = "Goal received: \"{metadata.get('goal', 'N/A')}\""
            elif message_type == "plan_ready":
                plan_text = metadata.get("llm_response", "No plan text available.")
                text = f"Here is the plan:\n{plan_text}"
                sender = "bot"
            elif message_type == "goal_completed":
                results = json.dumps(metadata.get("results", {}), indent=2)
                text = f"Goal completed. Result: {results}"
            elif message_type == "command_execution_start":
                text = f"Executing command: {metadata.get('command', 'N/A')}"
            elif message_type == "command_execution_end":
                status = metadata.get("status", "N/A")
                output = metadata.get("output", "")
                error = metadata.get("error", "")
                text = f"Command finished ({status}). Output: {output or error}"
            elif message_type == "error":
                text = f"Error: {metadata.get('message', 'Unknown error')}"
                sender = "error"
            elif message_type == "progress":
                text = f"Progress: {metadata.get('message', 'N/A')}"
            elif message_type == "llm_response":
                text = metadata.get("response", "N/A")
                sender = "bot"
            elif message_type == "user_message":
                text = metadata.get("message", "N/A")
                sender = "user"
            elif message_type == "thought":
                text = json.dumps(metadata.get("thought", {}), indent=2)
                sender = "thought"
            elif message_type == "tool_code":
                text = metadata.get("code", "N/A")
                sender = "tool-code"
            elif message_type == "tool_output":
                text = metadata.get("output", "N/A")
                sender = "tool-output"
            elif message_type == "settings_updated":
                text = "Settings updated successfully."
            elif message_type == "file_uploaded":
                text = f"File uploaded: {metadata.get('filename', 'N/A')}"
            elif message_type == "knowledge_base_update":
                text = f"Knowledge Base updated: {metadata.get('type', 'N/A')}"
            elif message_type == "llm_status":
                status = metadata.get("status", "N/A")
                model = metadata.get("model", "N/A")
                message = metadata.get("message", "")
                text = f"LLM ({model}) connection {status}. {message}"
                if status == "disconnected":
                    sender = "error"
            elif message_type == "diagnostics_report":
                text = f"Diagnostics Report: {json.dumps(metadata, indent=2)}"
            elif message_type == "user_permission_request":
                text = f"User Permission Request: {json.dumps(metadata, indent=2)}"
            elif message_type == "workflow_step_started":
                workflow_id = metadata.get("workflow_id", "N/A")[:8]
                step_desc = metadata.get("description", "N/A")
                text = f"🔄 Workflow {workflow_id}: Started step - {step_desc}"
                sender = "workflow"
            elif message_type == "workflow_step_completed":
                workflow_id = metadata.get("workflow_id", "N/A")[:8]
                step_desc = metadata.get("description", "N/A")
                result = metadata.get("result", "Completed")
                text = (
                    f"✅ Workflow {workflow_id}: Completed step - {step_desc}. "
                    f"Result: {result}"
                )
                sender = "workflow"
            elif message_type == "workflow_approval_required":
                workflow_id = metadata.get("workflow_id", "N/A")[:8]
                step_desc = metadata.get("description", "N/A")
                text = f"⏸️ Workflow {workflow_id}: Approval required for - {step_desc}"
                sender = "workflow"
            elif message_type == "workflow_completed":
                workflow_id = metadata.get("workflow_id", "N/A")[:8]
                total_steps = metadata.get("total_steps", 0)
                text = (
                    f"🎉 Workflow {workflow_id}: Completed successfully with "
                    f"{total_steps} steps"
                )
                sender = "workflow"
            elif message_type == "workflow_failed":
                workflow_id = metadata.get("workflow_id", "N/A")[:8]
                error = metadata.get("error", "Unknown error")
                text = f"❌ Workflow {workflow_id}: Failed - {error}"
                sender = "workflow-error"
            elif message_type == "workflow_cancelled":
                workflow_id = metadata.get("workflow_id", "N/A")[:8]
                text = f"🛑 Workflow {workflow_id}: Cancelled by user"
                sender = "workflow"

            # Add to chat history if we have meaningful text
            if text:
                chat_history_manager.add_message(sender, text, message_type, metadata)

        except RuntimeError as e:
            logger.error(f"Error sending to WebSocket: {e}")
            # Connection may have been closed, continue silently

    # Register the broadcast function with the event manager
    event_manager.register_websocket_broadcast(broadcast_event)

    try:
        # Keep connection alive and handle incoming messages
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
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
