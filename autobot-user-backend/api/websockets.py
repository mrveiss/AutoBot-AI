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

from backend.type_defs.common import SKIP_WEBSOCKET_PERSISTENCE_TYPES
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

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
    logger.info("Received command approval via WebSocket: %s", data)

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

        logger.info("Command approval result: %s", result.get("status"))

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
        logger.error("Error processing approval: %s", approval_error, exc_info=True)
        await websocket.send_json(
            {
                "type": "approval_error",
                "payload": {"error": str(approval_error)},
            }
        )


async def _add_to_chat_history(
    chat_history_manager, message_type: str, raw_data: dict
) -> None:
    """Add message to chat history if conditions are met (Issue #315 - extracted).

    Args:
        chat_history_manager: Chat history manager instance
        message_type: The message type
        raw_data: The message data
    """
    text, sender = _format_event_for_chat(message_type, raw_data)

    # Add to chat history if we have meaningful text and chat_history_manager is available
    # Issue #350 Root Cause Fix: Skip message types that are explicitly persisted elsewhere
    if (
        text
        and chat_history_manager
        and message_type not in SKIP_WEBSOCKET_PERSISTENCE_TYPES
    ):
        try:
            await chat_history_manager.add_message(sender, text, message_type, raw_data)
        except Exception as e:
            logger.error("Failed to add message to chat history: %s", e)


async def _create_broadcast_event_handler(websocket: WebSocket, chat_history_manager):
    """Create broadcast event handler function (Issue #315 - extracted).

    Args:
        websocket: The WebSocket connection
        chat_history_manager: Chat history manager instance

    Returns:
        Async function that broadcasts events
    """

    async def broadcast_event(event_data: dict):
        """Broadcast event to WebSocket client and add to chat history."""
        try:
            await websocket.send_json(event_data)

            # Add event to chat history manager
            message_type = event_data.get("type", "default")
            raw_data = event_data.get("payload", {})

            await _add_to_chat_history(chat_history_manager, message_type, raw_data)

        except RuntimeError as e:
            if "websocket" in str(e).lower() or "connection" in str(e).lower():
                logger.info("WebSocket connection lost during broadcast: %s", e)
            else:
                logger.error("Runtime error in WebSocket broadcast: %s", e)
        except Exception as e:
            logger.error("Unexpected error in WebSocket broadcast: %s", e)

    return broadcast_event


async def _websocket_message_receive_loop(websocket: WebSocket) -> None:
    """Main message receive loop for WebSocket (Issue #315 - extracted).

    Args:
        websocket: The WebSocket connection
    """
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
            logger.error("Error receiving message: %s", e)
            # Check if it's a connection error vs other error
            if "connection" in str(e).lower() or "closed" in str(e).lower():
                logger.info("Connection-related error detected, ending WebSocket loop")
                break
            else:
                # Other errors, continue trying
                continue

        # Issue #336: Use extracted helper for message handling
        await _handle_websocket_message(websocket, message)


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
            logger.debug("Received user message via WebSocket: %s", data)
        elif msg_type == "pong":
            logger.debug("Received pong from client")
        elif msg_type == "command_approval":
            await _handle_command_approval(websocket, data)
    except json.JSONDecodeError:
        logger.warning("Received invalid JSON via WebSocket: %s", message)


# Connected WebSocket clients for NPU workers
_npu_worker_ws_clients: list[WebSocket] = []
_npu_events_subscribed = False

# Lock for thread-safe access to _npu_worker_ws_clients
_ws_clients_lock = asyncio.Lock()

# Lock for thread-safe access to _npu_events_subscribed (Issue #513 - race condition fix)
import threading

_npu_events_lock = threading.Lock()


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
                logger.error("Error in test WebSocket: %s", e)
                break

    except Exception as e:
        logger.error("Test WebSocket error: %s", e)
    finally:
        logger.info("Test WebSocket disconnected")


def _get_chat_history_manager(websocket: WebSocket):
    """
    Get chat_history_manager from WebSocket app.state.

    Issue #665: Extracted from websocket_endpoint to reduce function length.

    Args:
        websocket: WebSocket connection

    Returns:
        chat_history_manager or None if not available
    """
    try:
        if hasattr(websocket.scope.get("app"), "state"):
            manager = getattr(
                websocket.scope["app"].state, "chat_history_manager", None
            )
            if manager:
                logger.info("Successfully accessed chat_history_manager from app.state")
            else:
                logger.warning("chat_history_manager not available in app.state")
            return manager
        logger.warning("app.state not available in WebSocket scope")
        return None
    except Exception as e:
        logger.error("Failed to access chat_history_manager: %s", e)
        return None


def _register_event_manager_broadcast(broadcast_event: Callable) -> None:
    """
    Register broadcast function with event manager.

    Issue #665: Extracted from websocket_endpoint to reduce function length.

    Args:
        broadcast_event: Broadcast callback function
    """
    try:
        from event_manager import event_manager

        event_manager.register_websocket_broadcast(broadcast_event)
        logger.info("Successfully registered WebSocket broadcast with event manager")
    except ImportError as e:
        logger.warning("Event manager not available, continuing without it: %s", e)
    except Exception as e:
        logger.warning("Failed to register WebSocket broadcast, continuing: %s", e)


def _unregister_event_manager_broadcast() -> None:
    """
    Unregister broadcast function from event manager.

    Issue #665: Extracted from websocket_endpoint to reduce function length.
    """
    try:
        from event_manager import event_manager

        event_manager.register_websocket_broadcast(None)
        logger.info("WebSocket broadcast unregistered from event manager")
    except ImportError:
        logger.debug("Event manager not available for cleanup")
    except Exception as e:
        logger.error("Error during event manager cleanup: %s", e)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_endpoint",
    error_code_prefix="WEBSOCKETS",
)
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event stream between backend and frontend.

    Issue #665: Refactored to use extracted helper methods.
    """
    try:
        await websocket.accept()
        logger.info("WebSocket connected from client: %s", websocket.client)

        await websocket.send_json(
            {
                "type": "connection_established",
                "payload": {"message": "WebSocket connected successfully"},
            }
        )
    except Exception as e:
        logger.error("Failed to accept WebSocket connection: %s", e, exc_info=True)
        return

    # Issue #665: Use helper for chat history manager access
    chat_history_manager = _get_chat_history_manager(websocket)

    broadcast_event = await _create_broadcast_event_handler(
        websocket, chat_history_manager
    )

    # Issue #665: Use helper for event manager registration
    _register_event_manager_broadcast(broadcast_event)

    try:
        await _websocket_message_receive_loop(websocket)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
    finally:
        # Issue #665: Use helper for cleanup
        _unregister_event_manager_broadcast()
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
        logger.info("NPU Worker WebSocket connected from client: %s", websocket.client)

        # Add to connected clients (thread-safe)
        async with _ws_clients_lock:
            _npu_worker_ws_clients.append(websocket)

        # Send initial worker list (Issue #315 - refactored)
        await _send_initial_worker_list(websocket)

        # Keep connection alive and handle incoming messages (Issue #315 - refactored)
        await _npu_message_receive_loop(websocket)

    except Exception as e:
        logger.error("NPU Worker WebSocket error: %s", e, exc_info=True)
    finally:
        # Remove from connected clients (thread-safe)
        async with _ws_clients_lock:
            if websocket in _npu_worker_ws_clients:
                _npu_worker_ws_clients.remove(websocket)
        logger.info("NPU Worker WebSocket connection cleanup completed")


# Issue #315: NPU worker event type mapping (dispatch table pattern)
_NPU_EVENT_TYPE_MAP = {
    "worker.status.changed": lambda data: {
        "type": "worker_update",
        "worker": data.get("worker", {}),
    },
    "worker.added": lambda data: {
        "type": "worker_added",
        "worker": data.get("worker", {}),
    },
    "worker.updated": lambda data: {
        "type": "worker_update",
        "worker": data.get("worker", {}),
    },
    "worker.removed": lambda data: {
        "type": "worker_removed",
        "worker_id": data.get("worker_id", ""),
    },
    "worker.metrics.updated": lambda data: {
        "type": "worker_metrics_update",
        "worker_id": data.get("worker_id", ""),
        "metrics": data.get("data", {}).get("metrics", {}),
    },
}


def _prepare_npu_worker_message(event_data: dict) -> dict:
    """Prepare WebSocket message from NPU worker event (Issue #315 - refactored).

    Args:
        event_data: Event data containing type and payload

    Returns:
        Formatted message dict, or empty dict if event type unknown
    """
    event_type = event_data.get("event", "")
    formatter = _NPU_EVENT_TYPE_MAP.get(event_type)
    return formatter(event_data) if formatter else {}


async def broadcast_npu_worker_event(event_data: dict):
    """
    Broadcast NPU worker event to all connected WebSocket clients.

    Args:
        event_data: Event data containing type and payload
    """
    if not _npu_worker_ws_clients:
        return

    # Prepare message based on event type (Issue #315 - refactored)
    message = _prepare_npu_worker_message(event_data)
    if not message:
        return

    # Broadcast to all connected clients (thread-safe) (Issue #315 - refactored)
    disconnected_clients = []

    async with _ws_clients_lock:
        clients_copy = list(_npu_worker_ws_clients)

    for client in clients_copy:
        success = await _broadcast_to_client(client, message)
        if not success:
            disconnected_clients.append(client)

    # Remove disconnected clients (thread-safe)
    await _cleanup_disconnected_clients(disconnected_clients)


def _format_worker_for_frontend(w) -> dict:
    """Format worker data for frontend consumption (Issue #372 - uses model method).

    Args:
        w: NPUWorkerDetails object

    Returns:
        Formatted worker dictionary
    """
    # Delegate to model method to reduce feature envy (Issue #372)
    return w.to_event_dict()


async def _send_initial_worker_list(websocket: WebSocket) -> None:
    """Send initial worker list to newly connected client (Issue #315 - extracted).

    Args:
        websocket: The WebSocket connection
    """
    try:
        from backend.services.npu_worker_manager import get_worker_manager

        worker_manager = await get_worker_manager()
        workers = await worker_manager.list_workers()

        # Convert workers to frontend format
        workers_data = [_format_worker_for_frontend(w) for w in workers]

        await websocket.send_json({"type": "initial_workers", "workers": workers_data})

    except Exception as e:
        logger.error("Failed to send initial worker list: %s", e, exc_info=True)


async def _npu_message_receive_loop(websocket: WebSocket) -> None:
    """Main message receive loop for NPU worker WebSocket (Issue #315 - extracted).

    Args:
        websocket: The WebSocket connection
    """
    while websocket.client_state == WebSocketState.CONNECTED:
        try:
            # No timeout - WebSocketDisconnect will be raised on disconnect
            message = await websocket.receive_text()
            await _handle_npu_websocket_message(websocket, message)

        except WebSocketDisconnect:
            logger.info("NPU Worker WebSocket client disconnected")
            break
        except Exception as e:
            logger.error("Error in NPU worker WebSocket: %s", e)
            if "connection" in str(e).lower() or "closed" in str(e).lower():
                logger.info("Connection-related error, ending WebSocket loop")
                break
            else:
                continue


async def _handle_npu_websocket_message(websocket: WebSocket, message: str) -> None:
    """Handle incoming NPU worker WebSocket message (Issue #315 - extracted).

    Args:
        websocket: The WebSocket connection
        message: The raw message string
    """
    try:
        data = json.loads(message)
        if data.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
        else:
            logger.debug("Received NPU worker WebSocket message: %s", data)
    except json.JSONDecodeError:
        logger.warning("Received invalid JSON via NPU worker WebSocket: %s", message)


async def _broadcast_to_client(client: WebSocket, message: dict) -> bool:
    """Broadcast message to a single client (Issue #315 - extracted).

    Args:
        client: The WebSocket client
        message: The message to send

    Returns:
        True if successful, False if client should be removed
    """
    try:
        if client.client_state == WebSocketState.CONNECTED:
            await client.send_json(message)
            return True
        return False
    except RuntimeError as e:
        logger.debug("WebSocket send failed (client disconnected): %s", e)
        return False
    except Exception as e:
        logger.error("Error broadcasting NPU worker event: %s", e)
        return False


async def _cleanup_disconnected_clients(disconnected_clients: list) -> None:
    """Remove disconnected clients from the global list (Issue #315 - extracted).

    Args:
        disconnected_clients: List of clients to remove
    """
    if not disconnected_clients:
        return

    async with _ws_clients_lock:
        for client in disconnected_clients:
            if client in _npu_worker_ws_clients:
                _npu_worker_ws_clients.remove(client)


def init_npu_worker_websocket():
    """
    Initialize NPU worker WebSocket by subscribing to events.
    Should be called during app startup. Thread-safe.

    Issue #513: Added thread-safe locking for global state modification.
    """
    global _npu_events_subscribed

    # Quick check without lock (optimization)
    if _npu_events_subscribed:
        logger.debug("NPU worker WebSocket events already subscribed")
        return

    # Thread-safe double-checked locking pattern (Issue #513 - race condition fix)
    with _npu_events_lock:
        # Double-check after acquiring lock
        if _npu_events_subscribed:
            logger.debug("NPU worker WebSocket events already subscribed (after lock)")
            return

        try:
            from event_manager import event_manager

            # Subscribe to all NPU worker events
            event_manager.subscribe(
                "npu.worker.status.changed", broadcast_npu_worker_event
            )
            event_manager.subscribe("npu.worker.added", broadcast_npu_worker_event)
            event_manager.subscribe("npu.worker.updated", broadcast_npu_worker_event)
            event_manager.subscribe("npu.worker.removed", broadcast_npu_worker_event)
            event_manager.subscribe(
                "npu.worker.metrics.updated", broadcast_npu_worker_event
            )

            _npu_events_subscribed = True
            logger.info("NPU worker WebSocket event subscriptions initialized")

        except Exception as e:
            logger.error(
                "Failed to subscribe to NPU worker events: %s", e, exc_info=True
            )
