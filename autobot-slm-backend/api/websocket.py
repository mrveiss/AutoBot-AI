# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM WebSocket API Routes

Provides real-time updates for deployments and system events.
"""

import asyncio
import logging
import time
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.auth import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])


def _extract_ws_token(websocket: WebSocket) -> str | None:
    """Extract the JWT from a WebSocket connection.

    Prefers the Sec-WebSocket-Protocol subprotocol header
    (``['bearer', '<token>']``) so the token is never written to URL access
    logs.  Falls back to the ``?token=`` query param for backwards
    compatibility with older clients.
    """
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    if protocols:
        parts = [p.strip() for p in protocols.split(",")]
        if len(parts) == 2 and parts[0] == "bearer" and parts[1]:
            return parts[1]
    return websocket.query_params.get("token") or None


def _log_ws_reject_context(websocket: WebSocket, reason: str) -> None:
    """Log WebSocket rejection with origin/host/peer context for diagnosability.

    Called before closing a connection so that the next live 403 occurrence
    (e.g. from a proxy or environment-specific config) can be traced back to
    the exact request properties (GH#10459).

    Args:
        websocket: The incoming (not yet accepted) WebSocket.
        reason: Human-readable rejection reason for the log entry.
    """
    headers = websocket.headers
    logger.warning(
        "WebSocket rejected (%s) | path=%s origin=%r host=%r peer=%r proto=%r",
        reason,
        websocket.url.path,
        headers.get("origin", "-"),
        headers.get("host", "-"),
        websocket.client,
        headers.get("sec-websocket-protocol", "-")[:60],
    )


async def _authenticate_websocket_token(websocket: WebSocket) -> dict | None:
    """Authenticate a WebSocket connection.

    Extracts the JWT via subprotocol header (preferred) or query param
    (fallback), validates it, accepts the socket on success, and returns
    the decoded payload.  On failure, accepts then closes with code 4001
    so the browser receives a proper WS frame rather than an HTTP 403.

    NOTE: the close MUST be preceded by accept() so uvicorn sends a proper
    WebSocket close frame (code 4001) rather than converting an unaccepted
    close to HTTP 403 (GH#10459: uvicorn maps websocket.close-before-accept
    to HTTP 403, which is what the backend's websockets library reports as
    'server rejected WebSocket connection: HTTP 403').

    Args:
        websocket: The incoming WebSocket connection (not yet accepted).

    Returns:
        Decoded JWT payload dict, or ``None`` if authentication failed.
    """
    token = _extract_ws_token(websocket)
    if not token:
        _log_ws_reject_context(websocket, "missing token")
        await websocket.accept()
        await websocket.close(code=4001, reason="Authentication required")
        return None

    payload = await auth_service.decode_token_async(token)
    if not payload:
        _log_ws_reject_context(websocket, "invalid token")
        await websocket.accept()
        await websocket.close(code=4001, reason="Invalid or expired token")
        return None

    return payload


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """Accept a WebSocket connection and subscribe to a channel."""
        protocols = websocket.headers.get("sec-websocket-protocol", "")
        subprotocol = "bearer" if protocols.startswith("bearer") else None
        await websocket.accept(subprotocol=subprotocol)
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

    async def send_deployment_log(self, deployment_id: str, log_type: str, message: str) -> None:
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

    async def send_health_update(
        self,
        node_id: str,
        cpu: float,
        memory: float,
        disk: float,
        status: str,
        last_heartbeat: str = None,
    ) -> None:
        """Send health update to global and node-specific event channels."""
        from datetime import datetime, timezone

        message = {
            "type": "health_update",
            "node_id": node_id,
            "data": {
                "status": status,
                "cpu_percent": cpu,
                "memory_percent": memory,
                "disk_percent": disk,
                "last_heartbeat": last_heartbeat or datetime.now(timezone.utc).isoformat(),
            },
            "timestamp": asyncio.get_running_loop().time(),
        }
        # Broadcast to global channel
        await self.broadcast("events:global", message)
        # Broadcast to node-specific channel
        await self.broadcast(f"node:{node_id}", message)

    async def send_node_status(self, node_id: str, status: str, hostname: str = None) -> None:
        """Send node status change to global and node-specific event channels."""
        message = {
            "type": "node_status",
            "node_id": node_id,
            "data": {
                "status": status,
                "hostname": hostname,
            },
            "timestamp": asyncio.get_running_loop().time(),
        }
        # Broadcast to global channel
        await self.broadcast("events:global", message)
        # Broadcast to node-specific channel
        await self.broadcast(f"node:{node_id}", message)

    async def send_remediation_event(
        self, node_id: str, event_type: str, success: bool = None, message: str = None
    ) -> None:
        """Send remediation event to global and node-specific event channels."""
        event_message = {
            "type": "remediation_event",
            "node_id": node_id,
            "data": {
                "event_type": event_type,
                "success": success,
                "message": message,
            },
            "timestamp": asyncio.get_running_loop().time(),
        }
        # Broadcast to global channel
        await self.broadcast("events:global", event_message)
        # Broadcast to node-specific channel
        await self.broadcast(f"node:{node_id}", event_message)

    async def send_service_status(
        self,
        node_id: str,
        service_name: str,
        status: str,
        action: str = None,
        success: bool = True,
        message: str = None,
    ) -> None:
        """Send service status change to global and node-specific event channels."""
        event_message = {
            "type": "service_status",
            "node_id": node_id,
            "data": {
                "service_name": service_name,
                "status": status,
                "action": action,
                "success": success,
                "message": message,
            },
            "timestamp": asyncio.get_running_loop().time(),
        }
        # Broadcast to global channel
        await self.broadcast("events:global", event_message)
        # Broadcast to node-specific channel
        await self.broadcast(f"node:{node_id}", event_message)

    async def send_node_lifecycle_event(self, node_id: str, event_type: str, details: dict = None) -> None:
        """Send a general node lifecycle event (enrollment, deletion, etc.)."""
        event_message = {
            "type": "lifecycle_event",
            "node_id": node_id,
            "data": {
                "event_type": event_type,
                "details": details or {},
            },
            "timestamp": asyncio.get_running_loop().time(),
        }
        # Broadcast to global channel
        await self.broadcast("events:global", event_message)
        # Broadcast to node-specific channel
        await self.broadcast(f"node:{node_id}", event_message)

    async def send_provision_log(self, log_type: str, message: str) -> None:
        """Send a provisioning log line to watchers (#2754)."""
        await self.broadcast(
            "provision",
            {
                "type": "log",
                "log_type": log_type,
                "message": message,
            },
        )

    async def send_provision_status(
        self, status: str, stage: str = "", elapsed: float = 0, error: str | None = None
    ) -> None:
        """Send a provisioning status update to watchers (#2754)."""

        await self.broadcast(
            "provision",
            {
                "type": "status",
                "status": status,
                "stage": stage,
                "elapsed_seconds": round(elapsed, 1),
                "error": error,
                "timestamp": time.time(),
            },
        )


# Global connection manager instance
ws_manager = ConnectionManager()


@router.websocket("/deployments/{deployment_id}")
async def deployment_websocket(websocket: WebSocket, deployment_id: str):
    """WebSocket endpoint for watching deployment progress."""
    if not await _authenticate_websocket_token(websocket):
        return

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
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
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
    if not await _authenticate_websocket_token(websocket):
        return

    channel = "events:global"
    await ws_manager.connect(websocket, channel)

    try:
        await websocket.send_json({"type": "connected", "message": "Connected to event stream"})

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
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


@router.websocket("/nodes/{node_id}")
async def node_events_websocket(websocket: WebSocket, node_id: str):
    """
    WebSocket endpoint for watching a specific node's lifecycle events.

    Events include:
    - health_update: CPU, memory, disk metrics
    - node_status: Status changes (online, offline, degraded, error)
    - remediation_event: Auto-remediation attempts and results
    - service_status: Service start/stop/restart events
    - lifecycle_event: Node enrollment, deletion, configuration changes

    Clients receive only events for the specified node_id.
    """
    if not await _authenticate_websocket_token(websocket):
        return

    channel = f"node:{node_id}"
    await ws_manager.connect(websocket, channel)

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "node_id": node_id,
                "message": f"Connected to lifecycle events for node {node_id}",
            }
        )

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug("Client disconnected from node %s events", node_id)
    except Exception as e:
        logger.error("WebSocket error for node %s: %s", node_id, e)
    finally:
        await ws_manager.disconnect(websocket, channel)


@router.websocket("/provision")
async def provision_websocket(websocket: WebSocket):
    """WebSocket endpoint for watching provisioning progress (#2754)."""
    if not await _authenticate_websocket_token(websocket):
        return

    channel = "provision"
    await ws_manager.connect(websocket, channel)

    try:
        await websocket.send_json({"type": "connected", "message": "Connected to provision stream"})

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug("Client disconnected from provision stream")
    except Exception as e:
        logger.error("WebSocket error for provision: %s", e)
    finally:
        await ws_manager.disconnect(websocket, channel)
