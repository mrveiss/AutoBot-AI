# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WebSocket API Router for AutoBot

This module handles WebSocket connections for real-time event streaming
between the backend and frontend clients.
"""

import asyncio
import json
import logging
from typing import Callable, Dict, Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.type_defs.common import STREAMING_MESSAGE_TYPES
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter()


# Issue #336: Message type to text/sender mapping functions (extracted from elif chain)
def _format_goal_received(raw_data: dict) -> Tuple[str, str]:
    """Format goal_received event."""
    return f"Goal received: \"{raw_data.get('goal', 'N/A')}\"", "system"


def _format_plan_ready(raw_data: dict) -> Tuple[str, str]:
    """Format plan_ready event."""
    plan_text = raw_data.get("llm_response", "No plan text available.")
    return f"Here is the plan:\n{plan_text}", "bot"


def _format_goal_completed(raw_data: dict) -> Tuple[str, str]:
    """Format goal_completed event."""
    results = json.dumps(raw_data.get("results", {}), indent=2)
    return f"Goal completed. Result: {results}", "system"


def _format_command_execution_start(raw_data: dict) -> Tuple[str, str]:
    """Format command_execution_start event."""
    return f"Executing command: {raw_data.get('command', 'N/A')}", "system"


def _format_command_execution_end(raw_data: dict) -> Tuple[str, str]:
    """Format command_execution_end event."""
    status = raw_data.get("status", "N/A")
    output = raw_data.get("output", "")
    error = raw_data.get("error", "")
    return f"Command finished ({status}). Output: {output or error}", "system"


def _format_error(raw_data: dict) -> Tuple[str, str]:
    """Format error event."""
    return f"Error: {raw_data.get('message', 'Unknown error')}", "error"


def _format_progress(raw_data: dict) -> Tuple[str, str]:
    """Format progress event."""
    return f"Progress: {raw_data.get('message', 'N/A')}", "system"


def _format_llm_response(raw_data: dict) -> Tuple[str, str]:
    """Format llm_response event."""
    return raw_data.get("response", "N/A"), "bot"


def _format_user_message(raw_data: dict) -> Tuple[str, str]:
    """Format user_message event."""
    return raw_data.get("message", "N/A"), "user"


def _format_thought(raw_data: dict) -> Tuple[str, str]:
    """Format thought event."""
    return json.dumps(raw_data.get("thought", {}), indent=2), "thought"


def _format_tool_code(raw_data: dict) -> Tuple[str, str]:
    """Format tool_code event."""
    return raw_data.get("code", "N/A"), "tool-code"


def _format_tool_output(raw_data: dict) -> Tuple[str, str]:
    """Format tool_output event."""
    return raw_data.get("output", "N/A"), "tool-output"


def _format_settings_updated(raw_data: dict) -> Tuple[str, str]:
    """Format settings_updated event."""
    return "Settings updated successfully.", "system"


def _format_file_uploaded(raw_data: dict) -> Tuple[str, str]:
    """Format file_uploaded event."""
    return f"File uploaded: {raw_data.get('filename', 'N/A')}", "system"


def _format_knowledge_base_update(raw_data: dict) -> Tuple[str, str]:
    """Format knowledge_base_update event."""
    return f"Knowledge Base updated: {raw_data.get('type', 'N/A')}", "system"


def _format_llm_status(raw_data: dict) -> Tuple[str, str]:
    """Format llm_status event."""
    status = raw_data.get("status", "N/A")
    model = raw_data.get("model", "N/A")
    message = raw_data.get("message", "")
    sender = "error" if status == "disconnected" else "system"
    return f"LLM ({model}) connection {status}. {message}", sender


def _format_diagnostics_report(raw_data: dict) -> Tuple[str, str]:
    """Format diagnostics_report event."""
    return f"Diagnostics Report: {json.dumps(raw_data, indent=2)}", "system"


def _format_user_permission_request(raw_data: dict) -> Tuple[str, str]:
    """Format user_permission_request event."""
    return f"User Permission Request: {json.dumps(raw_data, indent=2)}", "system"


def _format_workflow_step_started(raw_data: dict) -> Tuple[str, str]:
    """Format workflow_step_started event."""
    workflow_id = raw_data.get("workflow_id", "N/A")[:8]
    step_desc = raw_data.get("description", "N/A")
    return f"🔄 Workflow {workflow_id}: Started step - {step_desc}", "workflow"


def _format_workflow_step_completed(raw_data: dict) -> Tuple[str, str]:
    """Format workflow_step_completed event."""
    workflow_id = raw_data.get("workflow_id", "N/A")[:8]
    step_desc = raw_data.get("description", "N/A")
    result = raw_data.get("result", "Completed")
    text = f"✅ Workflow {workflow_id}: Completed step - {step_desc}. Result: {result}"
    return text, "workflow"


def _format_workflow_approval_required(raw_data: dict) -> Tuple[str, str]:
    """Format workflow_approval_required event."""
    workflow_id = raw_data.get("workflow_id", "N/A")[:8]
    step_desc = raw_data.get("description", "N/A")
    return f"⏸️ Workflow {workflow_id}: Approval required for - {step_desc}", "workflow"


def _format_workflow_completed(raw_data: dict) -> Tuple[str, str]:
    """Format workflow_completed event."""
    workflow_id = raw_data.get("workflow_id", "N/A")[:8]
    total_steps = raw_data.get("total_steps", 0)
    text = f"🎉 Workflow {workflow_id}: Completed successfully with {total_steps} steps"
    return text, "workflow"


def _format_workflow_failed(raw_data: dict) -> Tuple[str, str]:
    """Format workflow_failed event."""
    workflow_id = raw_data.get("workflow_id", "N/A")[:8]
    error = raw_data.get("error", "Unknown error")
    return f"❌ Workflow {workflow_id}: Failed - {error}", "workflow-error"


def _format_workflow_cancelled(raw_data: dict) -> Tuple[str, str]:
    """Format workflow_cancelled event."""
    workflow_id = raw_data.get("workflow_id", "N/A")[:8]
    return f"🛑 Workflow {workflow_id}: Cancelled by user", "workflow"


# Issue #336: Dispatch table for message type formatting
MESSAGE_TYPE_FORMATTERS: Dict[str, Callable[[dict], Tuple[str, str]]] = {
    "goal_received": _format_goal_received,
    "plan_ready": _format_plan_ready,
    "goal_completed": _format_goal_completed,
    "command_execution_start": _format_command_execution_start,
    "command_execution_end": _format_command_execution_end,
    "error": _format_error,
    "progress": _format_progress,
    "llm_response": _format_llm_response,
    "user_message": _format_user_message,
    "thought": _format_thought,
    "tool_code": _format_tool_code,
    "tool_output": _format_tool_output,
    "settings_updated": _format_settings_updated,
    "file_uploaded": _format_file_uploaded,
    "knowledge_base_update": _format_knowledge_base_update,
    "llm_status": _format_llm_status,
    "diagnostics_report": _format_diagnostics_report,
    "user_permission_request": _format_user_permission_request,
    "workflow_step_started": _format_workflow_step_started,
    "workflow_step_completed": _format_workflow_step_completed,
    "workflow_approval_required": _format_workflow_approval_required,
    "workflow_completed": _format_workflow_completed,
    "workflow_failed": _format_workflow_failed,
    "workflow_cancelled": _format_workflow_cancelled,
}


def _format_event_for_chat(
    message_type: str, raw_data: dict
) -> Tuple[Optional[str], str]:
    """Format event data for chat history (Issue #336 - extracted dispatch helper).

    Args:
        message_type: The event type
        raw_data: The event payload

    Returns:
        Tuple of (formatted_text, sender) or (None, "system") if no formatter
    """
    formatter = MESSAGE_TYPE_FORMATTERS.get(message_type)
    if formatter:
        return formatter(raw_data)
    return None, "system"


async def _handle_command_approval(websocket: WebSocket, data: dict) -> None:
    """Handle command approval message from frontend (Issue #336 - extracted helper).

    Args:
        websocket: The WebSocket connection
        data: The command approval data
    """
    logger.info(f"Received command approval via WebSocket: {data}")

    terminal_session_id = data.get("terminal_session_id")
    if not terminal_session_id:
        logger.warning("Received approval message without terminal_session_id")
        return

    approved = data.get("approved", False)
    user_id = data.get("user_id", "web_user")

    try:
        from backend.services.agent_terminal import AgentTerminalService

        service = AgentTerminalService()
        result = await service.approve_command(
            session_id=terminal_session_id,
            approved=approved,
            user_id=user_id,
        )

        logger.info(f"Command approval result: {result.get('status')}")

        await websocket.send_json(
            {
                "type": "approval_processed",
                "payload": {
                    "terminal_session_id": terminal_session_id,
                    "approved": approved,
                    "result": result,
                },
            }
        )
    except Exception as approval_error:
        logger.error(f"Error processing approval: {approval_error}", exc_info=True)
        await websocket.send_json(
            {
                "type": "approval_error",
                "payload": {"error": str(approval_error)},
            }
        )


async def _handle_websocket_message(websocket: WebSocket, message: str) -> None:
    """Handle incoming WebSocket message (Issue #336 - extracted helper).

    Args:
        websocket: The WebSocket connection
        message: The raw message string
    """
    try:
        data = json.loads(message)
        msg_type = data.get("type")

        if msg_type == "user_message":
            logger.debug(f"Received user message via WebSocket: {data}")
        elif msg_type == "pong":
            logger.debug("Received pong from client")
        elif msg_type == "command_approval":
            await _handle_command_approval(websocket, data)
    except json.JSONDecodeError:
        logger.warning(f"Received invalid JSON via WebSocket: {message}")

# Connected WebSocket clients for NPU workers
_npu_worker_ws_clients: list[WebSocket] = []
_npu_events_subscribed = False

# Lock for thread-safe access to _npu_worker_ws_clients
_ws_clients_lock = asyncio.Lock()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_test_endpoint",
    error_code_prefix="WEBSOCKETS",
)
@router.websocket("/ws-test")
async def websocket_test_endpoint(websocket: WebSocket):
    """Simple test WebSocket endpoint without event manager integration."""
    try:
        await websocket.accept()
        logger.info("Test WebSocket connected successfully")
        await websocket.send_json(
            {"type": "connected", "message": "Test connection successful"}
        )

        # ROOT CAUSE FIX: Replace timeout-based handling with event-driven pattern
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                # No timeout - WebSocketDisconnect will be raised on disconnect
                message = await websocket.receive_text()
                await websocket.send_json({"type": "echo", "message": message})
            except WebSocketDisconnect:
                logger.info("Test WebSocket client disconnected")
                break
            except Exception as e:
                logger.error(f"Error in test WebSocket: {e}")
                break

    except Exception as e:
        logger.error(f"Test WebSocket error: {e}")
    finally:
        logger.info("Test WebSocket disconnected")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_endpoint",
    error_code_prefix="WEBSOCKETS",
)
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event stream between backend and frontend.

    Handles:
    - Real-time event broadcasting from backend to frontend
    - Chat history integration for all events
    - Event type mapping and message formatting
    """
    chat_history_manager = None

    try:
        await websocket.accept()
        logger.info(f"WebSocket connected from client: {websocket.client}")

        # Send immediate connection confirmation
        await websocket.send_json(
            {
                "type": "connection_established",
                "payload": {"message": "WebSocket connected successfully"},
            }
        )

    except Exception as e:
        logger.error(f"Failed to accept WebSocket connection: {e}", exc_info=True)
        return

    # Access chat_history_manager from app.state via scope with error handling
    try:
        if hasattr(websocket.scope.get("app"), "state"):
            chat_history_manager = getattr(
                websocket.scope["app"].state, "chat_history_manager", None
            )
            if chat_history_manager:
                logger.info("Successfully accessed chat_history_manager from app.state")
            else:
                logger.warning("chat_history_manager not available in app.state")
        else:
            logger.warning("app.state not available in WebSocket scope")
    except Exception as e:
        logger.error(f"Failed to access chat_history_manager: {e}")
        # Don't send error to client here, just continue without chat history

    async def broadcast_event(event_data: dict):
        """
        Broadcast event to WebSocket client and add to chat history.

        Args:
            event_data (dict): Event data containing type and payload
        """
        try:
            await websocket.send_json(event_data)

            # Add event to chat history manager
            message_type = event_data.get("type", "default")
            raw_data = event_data.get("payload", {})

            # Issue #336: Use dispatch table instead of elif chain
            text, sender = _format_event_for_chat(message_type, raw_data)

            # Add to chat history if we have meaningful text and chat_history_manager is available
            # CRITICAL FIX: Skip streaming responses to prevent duplicate messages
            # Streaming responses are persisted once at completion in chat_workflow_manager.py
            if text and chat_history_manager and message_type not in STREAMING_MESSAGE_TYPES:
                try:
                    await chat_history_manager.add_message(
                        sender, text, message_type, raw_data
                    )
                except Exception as e:
                    logger.error(f"Failed to add message to chat history: {e}")

        except RuntimeError as e:
            if "websocket" in str(e).lower() or "connection" in str(e).lower():
                logger.info(f"WebSocket connection lost during broadcast: {e}")
            else:
                logger.error(f"Runtime error in WebSocket broadcast: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in WebSocket broadcast: {e}")

    # Register the broadcast function with the event manager
    try:
        from src.event_manager import event_manager

        event_manager.register_websocket_broadcast(broadcast_event)
        logger.info("Successfully registered WebSocket broadcast with event manager")
    except ImportError as e:
        logger.warning(f"Event manager not available, continuing without it: {e}")
        # Continue without event manager - this is not critical
    except Exception as e:
        logger.warning(f"Failed to register WebSocket broadcast, continuing: {e}")
        # Continue without event manager registration - this is not critical

    try:
        # Keep connection alive and handle incoming messages
        while True:
            # Check connection state before each operation
            if websocket.client_state != WebSocketState.CONNECTED:
                logger.info(
                    f"WebSocket state changed to {websocket.client_state}, ending loop"
                )
                break

            try:
                # ROOT CAUSE FIX: Replace timeout with natural message receive
                message = await websocket.receive_text()
                # No timeout needed - WebSocketDisconnect will be raised on disconnect
            except WebSocketDisconnect as e:
                logger.info(
                    f"WebSocket disconnected during receive: code={e.code}, reason='{e.reason or 'no reason'}'"
                )
                break
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                # Check if it's a connection error vs other error
                if "connection" in str(e).lower() or "closed" in str(e).lower():
                    logger.info(
                        "Connection-related error detected, ending WebSocket loop"
                    )
                    break
                else:
                    # Other errors, continue trying
                    continue

            # Issue #336: Use extracted helper for message handling
            await _handle_websocket_message(websocket, message)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Unregister the broadcast function when connection closes
        try:
            from src.event_manager import event_manager

            event_manager.register_websocket_broadcast(None)
            logger.info("WebSocket broadcast unregistered from event manager")
        except ImportError:
            logger.debug("Event manager not available for cleanup")
        except Exception as e:
            logger.error(f"Error during event manager cleanup: {e}")
        logger.info("WebSocket connection cleanup completed")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="npu_workers_websocket_endpoint",
    error_code_prefix="WEBSOCKETS",
)
@router.websocket("/ws/npu-workers")
async def npu_workers_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time NPU worker status updates.

    Handles:
    - Real-time worker status broadcasting
    - Worker added/updated/removed events
    - Worker metrics updates
    - Initial worker list on connection
    """
    try:
        await websocket.accept()
        logger.info(f"NPU Worker WebSocket connected from client: {websocket.client}")

        # Add to connected clients (thread-safe)
        async with _ws_clients_lock:
            _npu_worker_ws_clients.append(websocket)

        # Send initial worker list
        try:
            from backend.services.npu_worker_manager import get_worker_manager

            worker_manager = await get_worker_manager()
            workers = await worker_manager.list_workers()

            # Convert workers to frontend format
            workers_data = [
                {
                    "id": w.config.id,
                    "name": w.config.name,
                    "platform": w.config.platform,
                    "ip_address": (
                        w.config.url.split("//")[1].split(":")[0]
                        if "://" in w.config.url
                        else ""
                    ),
                    "port": (
                        int(w.config.url.split(":")[-1]) if ":" in w.config.url else 0
                    ),
                    "status": w.status.status.value,
                    "current_load": w.status.current_load,
                    "max_capacity": w.config.max_concurrent_tasks,
                    "uptime": f"{int(w.status.uptime_seconds)}s",
                    "performance_metrics": w.metrics.dict() if w.metrics else {},
                    "priority": w.config.priority,
                    "weight": w.config.weight,
                    "last_heartbeat": (
                        w.status.last_heartbeat.isoformat() + "Z"
                        if w.status.last_heartbeat
                        else ""
                    ),
                    "created_at": "",  # Not tracked
                }
                for w in workers
            ]

            await websocket.send_json(
                {"type": "initial_workers", "workers": workers_data}
            )

        except Exception as e:
            logger.error(f"Failed to send initial worker list: {e}", exc_info=True)

        # Keep connection alive and handle incoming messages
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                # No timeout - WebSocketDisconnect will be raised on disconnect
                message = await websocket.receive_text()

                # Handle ping/pong for connection keep-alive
                try:
                    data = json.loads(message)
                    if data.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    else:
                        logger.debug(f"Received NPU worker WebSocket message: {data}")
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received invalid JSON via NPU worker WebSocket: {message}"
                    )

            except WebSocketDisconnect:
                logger.info("NPU Worker WebSocket client disconnected")
                break
            except Exception as e:
                logger.error(f"Error in NPU worker WebSocket: {e}")
                if "connection" in str(e).lower() or "closed" in str(e).lower():
                    logger.info("Connection-related error, ending WebSocket loop")
                    break
                else:
                    continue

    except Exception as e:
        logger.error(f"NPU Worker WebSocket error: {e}", exc_info=True)
    finally:
        # Remove from connected clients (thread-safe)
        async with _ws_clients_lock:
            if websocket in _npu_worker_ws_clients:
                _npu_worker_ws_clients.remove(websocket)
        logger.info("NPU Worker WebSocket connection cleanup completed")


async def broadcast_npu_worker_event(event_data: dict):
    """
    Broadcast NPU worker event to all connected WebSocket clients.

    Args:
        event_data: Event data containing type and payload
    """
    if not _npu_worker_ws_clients:
        return

    # Prepare message based on event type
    event_type = event_data.get("event", "")
    message = {}

    if event_type == "worker.status.changed":
        message = {
            "type": "worker_update",
            "worker": event_data.get("worker", {}),
        }
    elif event_type == "worker.added":
        message = {
            "type": "worker_added",
            "worker": event_data.get("worker", {}),
        }
    elif event_type == "worker.updated":
        message = {
            "type": "worker_update",
            "worker": event_data.get("worker", {}),
        }
    elif event_type == "worker.removed":
        message = {
            "type": "worker_removed",
            "worker_id": event_data.get("worker_id", ""),
        }
    elif event_type == "worker.metrics.updated":
        message = {
            "type": "worker_metrics_update",
            "worker_id": event_data.get("worker_id", ""),
            "metrics": event_data.get("data", {}).get("metrics", {}),
        }

    if not message:
        return

    # Broadcast to all connected clients (thread-safe)
    disconnected_clients = []

    async with _ws_clients_lock:
        clients_copy = list(_npu_worker_ws_clients)

    for client in clients_copy:
        try:
            if client.client_state == WebSocketState.CONNECTED:
                await client.send_json(message)
            else:
                disconnected_clients.append(client)
        except RuntimeError as e:
            logger.debug(f"WebSocket send failed (client disconnected): {e}")
            disconnected_clients.append(client)
        except Exception as e:
            logger.error(f"Error broadcasting NPU worker event: {e}")
            disconnected_clients.append(client)

    # Remove disconnected clients (thread-safe)
    if disconnected_clients:
        async with _ws_clients_lock:
            for client in disconnected_clients:
                if client in _npu_worker_ws_clients:
                    _npu_worker_ws_clients.remove(client)


def init_npu_worker_websocket():
    """
    Initialize NPU worker WebSocket by subscribing to events.
    Should be called during app startup.
    """
    global _npu_events_subscribed

    if _npu_events_subscribed:
        logger.debug("NPU worker WebSocket events already subscribed")
        return

    try:
        from src.event_manager import event_manager

        # Subscribe to all NPU worker events
        event_manager.subscribe("npu.worker.status.changed", broadcast_npu_worker_event)
        event_manager.subscribe("npu.worker.added", broadcast_npu_worker_event)
        event_manager.subscribe("npu.worker.updated", broadcast_npu_worker_event)
        event_manager.subscribe("npu.worker.removed", broadcast_npu_worker_event)
        event_manager.subscribe(
            "npu.worker.metrics.updated", broadcast_npu_worker_event
        )

        _npu_events_subscribed = True
        logger.info("NPU worker WebSocket event subscriptions initialized")

    except Exception as e:
        logger.error(f"Failed to subscribe to NPU worker events: {e}", exc_info=True)
