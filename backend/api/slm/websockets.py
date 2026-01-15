# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM WebSocket API

Real-time event streaming for Service Lifecycle Manager:
- Node state changes
- Remediation alerts
- Health status updates
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm", tags=["SLM WebSocket"])


class SLMWebSocketManager:
    """
    Manages WebSocket connections for SLM real-time updates.

    Provides:
    - Connection lifecycle management
    - Event broadcasting to all connected clients
    - Subscription filtering by event type
    """

    def __init__(self):
        """Initialize WebSocket manager."""
        self._clients: Set[WebSocket] = set()
        self._client_subscriptions: Dict[WebSocket, Set[str]] = {}
        self._lock = asyncio.Lock()

        logger.info("SLM WebSocket manager initialized")

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)

    async def connect(
        self,
        websocket: WebSocket,
        subscriptions: Optional[List[str]] = None,
    ):
        """
        Accept WebSocket connection and register client.

        Args:
            websocket: WebSocket connection
            subscriptions: Optional list of event types to subscribe to
                          (default: all events)
        """
        await websocket.accept()

        async with self._lock:
            self._clients.add(websocket)
            if subscriptions:
                self._client_subscriptions[websocket] = set(subscriptions)
            else:
                # Subscribe to all events by default
                self._client_subscriptions[websocket] = {"*"}

        logger.info(
            "SLM WebSocket client connected (total=%d, subs=%s)",
            len(self._clients),
            subscriptions or ["*"],
        )

    async def disconnect(self, websocket: WebSocket):
        """
        Remove client on disconnect.

        Args:
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            self._clients.discard(websocket)
            self._client_subscriptions.pop(websocket, None)

        logger.info("SLM WebSocket client disconnected (total=%d)", len(self._clients))

    async def broadcast(self, event_type: str, data: Dict):
        """
        Broadcast event to all subscribed clients.

        Args:
            event_type: Event type (e.g., "state_change", "alert")
            data: Event data payload
        """
        if not self._clients:
            return

        message = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }

        disconnected = []

        async with self._lock:
            for client in self._clients:
                # Check subscription
                subs = self._client_subscriptions.get(client, set())
                if "*" not in subs and event_type not in subs:
                    continue

                try:
                    if client.client_state == WebSocketState.CONNECTED:
                        await client.send_json(message)
                except Exception as e:
                    logger.warning("Failed to send to SLM client: %s", e)
                    disconnected.append(client)

        # Cleanup disconnected clients
        for client in disconnected:
            await self.disconnect(client)

    async def broadcast_state_change(
        self,
        node_id: str,
        old_state: str,
        new_state: str,
        node_name: Optional[str] = None,
    ):
        """
        Broadcast node state change event.

        Args:
            node_id: Node ID
            old_state: Previous state
            new_state: New state
            node_name: Optional node name for display
        """
        await self.broadcast("state_change", {
            "node_id": node_id,
            "node_name": node_name,
            "old_state": old_state,
            "new_state": new_state,
        })

    async def broadcast_alert(
        self,
        node_id: str,
        level: str,
        details: Dict,
    ):
        """
        Broadcast alert event.

        Args:
            node_id: Node ID
            level: Alert level (info, warning, critical)
            details: Alert details
        """
        await self.broadcast("alert", {
            "node_id": node_id,
            "level": level,
            **details,
        })

    async def broadcast_health_update(
        self,
        node_id: str,
        health_data: Dict,
    ):
        """
        Broadcast health update event.

        Args:
            node_id: Node ID
            health_data: Health metrics
        """
        await self.broadcast("health_update", {
            "node_id": node_id,
            **health_data,
        })


# Global WebSocket manager instance
_ws_manager: Optional[SLMWebSocketManager] = None


def get_ws_manager() -> SLMWebSocketManager:
    """Get or create the singleton WebSocket manager."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = SLMWebSocketManager()
    return _ws_manager


@router.websocket("/events")
async def slm_events_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time SLM events.

    Connect to receive:
    - state_change: Node state transitions
    - alert: Remediation and health alerts
    - health_update: Node health metrics

    Query parameters:
    - subscribe: Comma-separated event types (default: all)
    """
    manager = get_ws_manager()

    # Parse subscriptions from query params
    subscribe_param = websocket.query_params.get("subscribe", "")
    subscriptions = [s.strip() for s in subscribe_param.split(",") if s.strip()]

    await manager.connect(websocket, subscriptions or None)

    try:
        while True:
            # Keep connection alive, handle incoming messages if needed
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0,
                )

                # Handle ping/pong
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.get("type") == "subscribe":
                    # Update subscriptions
                    new_subs = data.get("events", [])
                    if new_subs:
                        async with manager._lock:
                            manager._client_subscriptions[websocket] = set(new_subs)
                        await websocket.send_json({
                            "type": "subscribed",
                            "events": new_subs,
                        })

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("SLM WebSocket error: %s", e)
    finally:
        await manager.disconnect(websocket)


def create_reconciler_callbacks():
    """
    Create callbacks for the reconciler to broadcast events.

    Returns:
        Tuple of (on_state_change, on_alert) callbacks
    """
    manager = get_ws_manager()

    def on_state_change(node_id: str, old_state: str, new_state: str):
        """Callback for state changes."""
        asyncio.create_task(
            manager.broadcast_state_change(node_id, old_state, new_state)
        )

    def on_alert(node_id: str, level: str, details: Dict):
        """Callback for alerts."""
        asyncio.create_task(
            manager.broadcast_alert(node_id, level, details)
        )

    return on_state_change, on_alert


def get_health_update_callback():
    """
    Get callback for broadcasting health updates.

    Returns:
        Async function to broadcast health updates
    """
    manager = get_ws_manager()

    async def on_health_update(node_id: str, health_data: Dict):
        await manager.broadcast_health_update(node_id, health_data)

    return on_health_update
