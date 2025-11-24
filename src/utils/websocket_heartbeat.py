# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WebSocket Heartbeat System - Replaces timeout-based WebSocket handling
Uses heartbeat and event-driven patterns instead of arbitrary timeouts
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states"""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    HEARTBEAT_SENT = "heartbeat_sent"
    HEARTBEAT_RECEIVED = "heartbeat_received"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class HeartbeatConfig:
    """Configuration for heartbeat system"""

    heartbeat_interval: float = 30.0  # Send heartbeat every 30 seconds
    heartbeat_response_window: float = 5.0  # Wait 5 seconds for heartbeat response
    max_missed_heartbeats: int = 3  # Disconnect after 3 missed heartbeats
    ping_on_idle: bool = True  # Send ping when no messages received
    auto_reconnect: bool = True  # Enable auto-reconnect on disconnect


class WebSocketManager:
    """
    WebSocket manager with heartbeat-based connection monitoring.
    Replaces timeout-based message handling with event-driven patterns.
    """

    def __init__(self, config: Optional[HeartbeatConfig] = None):
        self.config = config or HeartbeatConfig()
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_states: Dict[str, ConnectionState] = {}
        self.last_heartbeat_sent: Dict[str, float] = {}
        self.last_heartbeat_received: Dict[str, float] = {}
        self.missed_heartbeats: Dict[str, int] = {}
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.message_handlers: Dict[str, Callable] = {}
        self._shutdown = False

    async def start_heartbeat_monitor(self):
        """Start the heartbeat monitoring task"""
        if self.heartbeat_task and not self.heartbeat_task.done():
            return  # Already running

        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("🫀 WebSocket heartbeat monitor started")

    async def stop_heartbeat_monitor(self):
        """Stop the heartbeat monitoring task"""
        self._shutdown = True
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        logger.info("🫀 WebSocket heartbeat monitor stopped")

    async def _heartbeat_loop(self):
        """Main heartbeat monitoring loop"""
        while not self._shutdown:
            try:
                current_time = time.time()

                # Check all active connections
                for connection_id in list(self.active_connections.keys()):
                    await self._check_connection_health(connection_id, current_time)

                # Wait before next check
                await asyncio.sleep(1.0)  # Check every second

            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(5.0)  # Wait longer on error

    async def _check_connection_health(self, connection_id: str, current_time: float):
        """Check health of a specific connection"""
        websocket = self.active_connections.get(connection_id)
        if not websocket:
            return

        state = self.connection_states.get(connection_id, ConnectionState.CONNECTED)
        last_heartbeat_sent = self.last_heartbeat_sent.get(connection_id, 0)
        last_heartbeat_received = self.last_heartbeat_received.get(
            connection_id, current_time
        )

        # Check if it's time to send heartbeat
        time_since_last_heartbeat = current_time - last_heartbeat_sent

        if time_since_last_heartbeat >= self.config.heartbeat_interval:
            await self._send_heartbeat(connection_id, websocket, current_time)

        # Check for missed heartbeats
        if state == ConnectionState.HEARTBEAT_SENT:
            response_time = current_time - last_heartbeat_sent
            if response_time > self.config.heartbeat_response_window:
                # Heartbeat response overdue
                missed_count = self.missed_heartbeats.get(connection_id, 0) + 1
                self.missed_heartbeats[connection_id] = missed_count

                logger.warning(f"Missed heartbeat #{missed_count} for {connection_id}")

                if missed_count >= self.config.max_missed_heartbeats:
                    await self._handle_connection_lost(connection_id)
                else:
                    # Reset state and try again
                    self.connection_states[connection_id] = ConnectionState.CONNECTED

    async def _send_heartbeat(
        self, connection_id: str, websocket: WebSocket, current_time: float
    ):
        """Send heartbeat ping to connection"""
        try:
            heartbeat_message = {
                "type": "heartbeat",
                "timestamp": current_time,
                "connection_id": connection_id,
            }

            await websocket.send_json(heartbeat_message)

            self.last_heartbeat_sent[connection_id] = current_time
            self.connection_states[connection_id] = ConnectionState.HEARTBEAT_SENT

            logger.debug(f"💓 Heartbeat sent to {connection_id}")

        except Exception as e:
            logger.error(f"Failed to send heartbeat to {connection_id}: {e}")
            await self._handle_connection_error(connection_id, e)

    async def _handle_connection_lost(self, connection_id: str):
        """Handle lost connection"""
        logger.warning(f"🔌 Connection lost: {connection_id}")

        # Clean up connection
        await self.disconnect(connection_id)

    async def _handle_connection_error(self, connection_id: str, error: Exception):
        """Handle connection errors"""
        logger.error(f"🚫 Connection error for {connection_id}: {error}")
        self.connection_states[connection_id] = ConnectionState.ERROR

        # Clean up on serious errors
        if isinstance(error, WebSocketDisconnect):
            await self.disconnect(connection_id)

    async def connect(self, websocket: WebSocket, connection_id: str) -> bool:
        """
        Accept WebSocket connection with heartbeat setup.
        No timeouts - either succeeds immediately or fails immediately.
        """
        try:
            await websocket.accept()

            # Register connection
            self.active_connections[connection_id] = websocket
            self.connection_states[connection_id] = ConnectionState.CONNECTED
            self.missed_heartbeats[connection_id] = 0

            current_time = time.time()
            self.last_heartbeat_received[connection_id] = current_time
            self.last_heartbeat_sent[connection_id] = current_time

            # Start heartbeat monitoring if not already running
            await self.start_heartbeat_monitor()

            # Send welcome message
            await websocket.send_json(
                {
                    "type": "connection_established",
                    "connection_id": connection_id,
                    "timestamp": current_time,
                    "heartbeat_interval": self.config.heartbeat_interval,
                }
            )

            logger.info(f"✅ WebSocket connected: {connection_id}")
            return True

        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            return False

    async def disconnect(self, connection_id: str):
        """Disconnect and clean up connection"""
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]

            try:
                # Send disconnect message if possible
                if self.connection_states.get(connection_id) not in [
                    ConnectionState.ERROR,
                    ConnectionState.DISCONNECTED,
                ]:
                    await websocket.send_json(
                        {
                            "type": "disconnecting",
                            "connection_id": connection_id,
                            "timestamp": time.time(),
                        }
                    )
            except Exception:
                pass  # Ignore errors when disconnecting

            # Clean up
            del self.active_connections[connection_id]
            del self.connection_states[connection_id]
            del self.missed_heartbeats[connection_id]
            if connection_id in self.last_heartbeat_sent:
                del self.last_heartbeat_sent[connection_id]
            if connection_id in self.last_heartbeat_received:
                del self.last_heartbeat_received[connection_id]

            logger.info(f"🔌 WebSocket disconnected: {connection_id}")

    async def handle_message(self, connection_id: str, message: str) -> bool:
        """
        Handle incoming message with heartbeat processing.
        Returns True if message was handled, False if connection should close.
        """
        if connection_id not in self.active_connections:
            return False

        current_time = time.time()
        self.last_heartbeat_received[connection_id] = current_time

        try:
            # Parse message
            try:
                message_data = json.loads(message)
            except json.JSONDecodeError:
                # Handle plain text messages
                message_data = {"type": "text", "content": message}

            message_type = message_data.get("type", "unknown")

            # Handle heartbeat responses
            if message_type == "heartbeat_response":
                await self._handle_heartbeat_response(
                    connection_id, message_data, current_time
                )
                return True

            # Handle other message types
            if message_type in self.message_handlers:
                handler = self.message_handlers[message_type]
                await handler(connection_id, message_data)
            else:
                # Default echo behavior
                await self._echo_message(connection_id, message_data)

            return True

        except Exception as e:
            logger.error(f"Error handling message from {connection_id}: {e}")
            return False

    async def _handle_heartbeat_response(
        self, connection_id: str, message_data: Dict[str, Any], current_time: float
    ):
        """Handle heartbeat response from client"""
        logger.debug(f"💓 Heartbeat response received from {connection_id}")

        # Reset missed heartbeat count
        self.missed_heartbeats[connection_id] = 0
        self.connection_states[connection_id] = ConnectionState.HEARTBEAT_RECEIVED

        # Optional: Send acknowledgment
        websocket = self.active_connections[connection_id]
        await websocket.send_json({"type": "heartbeat_ack", "timestamp": current_time})

    async def _echo_message(self, connection_id: str, message_data: Dict[str, Any]):
        """Default echo behavior for unknown message types"""
        websocket = self.active_connections[connection_id]
        await websocket.send_json(
            {"type": "echo", "original": message_data, "timestamp": time.time()}
        )

    def register_message_handler(self, message_type: str, handler: Callable):
        """Register handler for specific message types"""
        self.message_handlers[message_type] = handler
        logger.info(f"📝 Registered handler for message type: {message_type}")

    async def broadcast_message(
        self, message: Dict[str, Any], exclude: Optional[Set[str]] = None
    ):
        """Broadcast message to all active connections"""
        exclude = exclude or set()
        message["timestamp"] = time.time()

        for connection_id, websocket in self.active_connections.items():
            if connection_id not in exclude:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast to {connection_id}: {e}")

    async def send_message(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """Send message to specific connection"""
        if connection_id not in self.active_connections:
            return False

        websocket = self.active_connections[connection_id]
        message["timestamp"] = time.time()

        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {connection_id}: {e}")
            return False

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about active connections"""
        current_time = time.time()

        stats = {
            "total_connections": len(self.active_connections),
            "connection_states": {},
            "heartbeat_health": {},
        }

        for connection_id in self.active_connections.keys():
            state = self.connection_states.get(connection_id, ConnectionState.CONNECTED)
            stats["connection_states"][connection_id] = state.value

            last_heartbeat = self.last_heartbeat_received.get(
                connection_id, current_time
            ),
            missed_count = self.missed_heartbeats.get(connection_id, 0)

            stats["heartbeat_health"][connection_id] = {
                "seconds_since_last_heartbeat": current_time - last_heartbeat,
                "missed_heartbeats": missed_count,
                "state": state.value,
            }

        return stats


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


async def create_websocket_handler(websocket: WebSocket, connection_id: str):
    """
    Create event-driven WebSocket handler - no timeouts, just heartbeat monitoring
    """

    # Connect with heartbeat setup
    if not await websocket_manager.connect(websocket, connection_id):
        return

    try:
        # Event-driven message loop - no timeouts
        while connection_id in websocket_manager.active_connections:
            try:
                # Wait for message - will raise WebSocketDisconnect on disconnect
                message = await websocket.receive_text()

                # Handle message through manager
                if not await websocket_manager.handle_message(connection_id, message):
                    break  # Handler indicated connection should close

            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket disconnected normally: {connection_id}")
                break

            except Exception as e:
                logger.error(f"❌ WebSocket error for {connection_id}: {e}")
                break

    finally:
        await websocket_manager.disconnect(connection_id)
