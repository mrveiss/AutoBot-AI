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

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected WebSocket clients for NPU workers
_npu_worker_ws_clients: list[WebSocket] = []
_npu_events_subscribed = False


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
            sender = "system"
            text = ""
            message_type = event_data.get("type", "default")
            raw_data = event_data.get("payload", {})

            # Map event types to human-readable chat messages
            if message_type == "goal_received":
                text = "Goal received: \"{raw_data.get('goal', 'N/A')}\""
            elif message_type == "plan_ready":
                plan_text = raw_data.get("llm_response", "No plan text available.")
                text = f"Here is the plan:\n{plan_text}"
                sender = "bot"
            elif message_type == "goal_completed":
                results = json.dumps(raw_data.get("results", {}), indent=2)
                text = f"Goal completed. Result: {results}"
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
            elif message_type == "workflow_step_started":
                workflow_id = raw_data.get("workflow_id", "N/A")[:8]
                step_desc = raw_data.get("description", "N/A")
                text = f"🔄 Workflow {workflow_id}: Started step - {step_desc}"
                sender = "workflow"
            elif message_type == "workflow_step_completed":
                workflow_id = raw_data.get("workflow_id", "N/A")[:8]
                step_desc = raw_data.get("description", "N/A")
                result = raw_data.get("result", "Completed")
                text = (
                    f"✅ Workflow {workflow_id}: Completed step - {step_desc}. "
                    f"Result: {result}"
                )
                sender = "workflow"
            elif message_type == "workflow_approval_required":
                workflow_id = raw_data.get("workflow_id", "N/A")[:8]
                step_desc = raw_data.get("description", "N/A")
                text = f"⏸️ Workflow {workflow_id}: Approval required for - {step_desc}"
                sender = "workflow"
            elif message_type == "workflow_completed":
                workflow_id = raw_data.get("workflow_id", "N/A")[:8]
                total_steps = raw_data.get("total_steps", 0)
                text = (
                    f"🎉 Workflow {workflow_id}: Completed successfully with "
                    f"{total_steps} steps"
                )
                sender = "workflow"
            elif message_type == "workflow_failed":
                workflow_id = raw_data.get("workflow_id", "N/A")[:8]
                error = raw_data.get("error", "Unknown error")
                text = f"❌ Workflow {workflow_id}: Failed - {error}"
                sender = "workflow-error"
            elif message_type == "workflow_cancelled":
                workflow_id = raw_data.get("workflow_id", "N/A")[:8]
                text = f"🛑 Workflow {workflow_id}: Cancelled by user"
                sender = "workflow"

            # Add to chat history if we have meaningful text and chat_history_manager is available
            if text and chat_history_manager:
                try:
                    chat_history_manager.add_message(
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
                logger.info(f"WebSocket state changed to {websocket.client_state}, ending loop")
                break
                
            try:
                # ROOT CAUSE FIX: Replace timeout with natural message receive
                message = await websocket.receive_text()
                # No timeout needed - WebSocketDisconnect will be raised on disconnect
            except WebSocketDisconnect as e:
                logger.info(f"WebSocket disconnected during receive: code={e.code}, reason='{e.reason or 'no reason'}'")
                break
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                # Check if it's a connection error vs other error
                if "connection" in str(e).lower() or "closed" in str(e).lower():
                    logger.info("Connection-related error detected, ending WebSocket loop")
                    break
                else:
                    # Other errors, continue trying
                    continue

            try:
                data = json.loads(message)
                if data.get("type") == "user_message":
                    # Handle user messages if needed
                    # For now, just log them
                    logger.debug(f"Received user message via WebSocket: {data}")
                elif data.get("type") == "pong":
                    # Client responded to ping
                    logger.debug("Received pong from client")
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON via WebSocket: {message}")

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

        # Add to connected clients
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
                    "ip_address": w.config.url.split("//")[1].split(":")[0]
                    if "://" in w.config.url
                    else "",
                    "port": int(w.config.url.split(":")[-1])
                    if ":" in w.config.url
                    else 0,
                    "status": w.status.status.value,
                    "current_load": w.status.current_load,
                    "max_capacity": w.config.max_concurrent_tasks,
                    "uptime": f"{int(w.status.uptime_seconds)}s",
                    "performance_metrics": w.metrics.dict() if w.metrics else {},
                    "priority": w.config.priority,
                    "weight": w.config.weight,
                    "last_heartbeat": w.status.last_heartbeat.isoformat() + "Z"
                    if w.status.last_heartbeat
                    else "",
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
                        logger.debug(
                            f"Received NPU worker WebSocket message: {data}"
                        )
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
        # Remove from connected clients
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

    # Broadcast to all connected clients
    disconnected_clients = []

    for client in _npu_worker_ws_clients:
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

    # Remove disconnected clients
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
        event_manager.subscribe("npu.worker.metrics.updated", broadcast_npu_worker_event)

        _npu_events_subscribed = True
        logger.info("NPU worker WebSocket event subscriptions initialized")

    except Exception as e:
        logger.error(f"Failed to subscribe to NPU worker events: {e}", exc_info=True)
