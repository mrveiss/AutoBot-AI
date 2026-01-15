# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM WebSocket API Routes

Provides real-time updates for deployments and system events.
"""

import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """Accept a WebSocket connection and subscribe to a channel."""
        await websocket.accept()
        async with self._lock:
            if channel not in self._connections:
                self._connections[channel] = set()
            self._connections[channel].add(websocket)
        logger.debug("WebSocket connected to channel: %s", channel)

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """Remove a WebSocket from a channel."""
        async with self._lock:
            if channel in self._connections:
                self._connections[channel].discard(websocket)
                if not self._connections[channel]:
                    del self._connections[channel]
        logger.debug("WebSocket disconnected from channel: %s", channel)

    async def broadcast(self, channel: str, message: dict) -> None:
        """Send a message to all connections on a channel."""
        async with self._lock:
            connections = self._connections.get(channel, set()).copy()

        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if channel in self._connections:
                        self._connections[channel].discard(ws)

    async def send_to_deployment(self, deployment_id: str, message: dict) -> None:
        """Send a message to all watchers of a specific deployment."""
        await self.broadcast(f"deployment:{deployment_id}", message)

    async def send_deployment_log(
        self, deployment_id: str, log_type: str, message: str
    ) -> None:
        """Send a log line to deployment watchers."""
        await self.send_to_deployment(
            deployment_id,
            {
                "type": "log",
                "log_type": log_type,
                "message": message,
                "deployment_id": deployment_id,
            },
        )

    async def send_deployment_status(
        self, deployment_id: str, status: str, progress: int = 0, error: str = None
    ) -> None:
        """Send a status update to deployment watchers."""
        await self.send_to_deployment(
            deployment_id,
            {
                "type": "status",
                "status": status,
                "progress": progress,
                "error": error,
                "deployment_id": deployment_id,
            },
        )


# Global connection manager instance
ws_manager = ConnectionManager()


@router.websocket("/deployments/{deployment_id}")
async def deployment_websocket(websocket: WebSocket, deployment_id: str):
    """WebSocket endpoint for watching deployment progress."""
    channel = f"deployment:{deployment_id}"
    await ws_manager.connect(websocket, channel)

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "deployment_id": deployment_id,
                "message": "Connected to deployment stream",
            }
        )

        # Keep connection alive and handle any client messages
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=30.0
                )
                # Handle ping/pong for keepalive
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug("Client disconnected from deployment: %s", deployment_id)
    except Exception as e:
        logger.error("WebSocket error for deployment %s: %s", deployment_id, e)
    finally:
        await ws_manager.disconnect(websocket, channel)


@router.websocket("/events")
async def events_websocket(websocket: WebSocket):
    """WebSocket endpoint for global system events."""
    channel = "events:global"
    await ws_manager.connect(websocket, channel)

    try:
        await websocket.send_json(
            {"type": "connected", "message": "Connected to event stream"}
        )

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=30.0
                )
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug("Client disconnected from events")
    except Exception as e:
        logger.error("WebSocket error for events: %s", e)
    finally:
        await ws_manager.disconnect(websocket, channel)
