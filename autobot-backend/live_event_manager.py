# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Live Event Manager - Scoped Real-Time Events (#1408)

In-memory channel router for WebSocket-based entity-scoped event streaming.
Supports channels: agent:{id}, task:{id}, workflow:{id}, global
"""

import asyncio
import logging
from typing import Dict, Set

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

_VALID_PREFIXES = {"agent", "task", "workflow", "global"}


def _is_valid_channel(channel: str) -> bool:
    """Return True if channel matches agent:{id}, task:{id}, workflow:{id}, or global."""
    if channel == "global":
        return True
    parts = channel.split(":", 1)
    return len(parts) == 2 and parts[0] in _VALID_PREFIXES and bool(parts[1])


class LiveEventManager:
    """In-memory channel router for scoped WebSocket events."""

    def __init__(self) -> None:
        self._subscriptions: Dict[str, Set[WebSocket]] = {}
        self._client_channels: Dict[int, Set[str]] = {}
        self._lock = asyncio.Lock()
        self._event_counters: Dict[str, int] = {}

    def _ws_key(self, ws: WebSocket) -> int:
        return id(ws)

    async def subscribe(self, ws: WebSocket, channel: str) -> bool:
        """Subscribe a WebSocket to a channel. Returns False if channel is invalid."""
        if not _is_valid_channel(channel):
            logger.warning("Rejected invalid channel subscription: %s", channel)
            return False
        async with self._lock:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = set()
            self._subscriptions[channel].add(ws)
            key = self._ws_key(ws)
            if key not in self._client_channels:
                self._client_channels[key] = set()
            self._client_channels[key].add(channel)
        logger.debug("Client subscribed to channel: %s", channel)
        return True

    async def unsubscribe(self, ws: WebSocket, channel: str) -> None:
        """Remove a WebSocket from a channel."""
        async with self._lock:
            if channel in self._subscriptions:
                self._subscriptions[channel].discard(ws)
                if not self._subscriptions[channel]:
                    del self._subscriptions[channel]
            key = self._ws_key(ws)
            if key in self._client_channels:
                self._client_channels[key].discard(channel)
        logger.debug("Client unsubscribed from channel: %s", channel)

    async def remove_client(self, ws: WebSocket) -> None:
        """Remove a disconnected client from all subscriptions."""
        async with self._lock:
            key = self._ws_key(ws)
            channels = self._client_channels.pop(key, set())
            for channel in channels:
                if channel in self._subscriptions:
                    self._subscriptions[channel].discard(ws)
                    if not self._subscriptions[channel]:
                        del self._subscriptions[channel]
        logger.debug("Client removed from all channel subscriptions")

    def _next_event_id(self, channel: str) -> int:
        """Return next auto-incrementing event ID for channel."""
        self._event_counters[channel] = self._event_counters.get(channel, 0) + 1
        return self._event_counters[channel]

    async def publish(self, channel: str, event_type: str, payload: dict) -> int:
        """Publish event to channel subscribers and global subscribers."""
        if not _is_valid_channel(channel):
            logger.warning("Publish to invalid channel ignored: %s", channel)
            return 0
        event_id = self._next_event_id(channel)
        message = {
            "type": "live_event",
            "channel": channel,
            "event_type": event_type,
            "event_id": event_id,
            "payload": payload,
        }
        async with self._lock:
            recipients: Set[WebSocket] = set()
            recipients.update(self._subscriptions.get(channel, set()))
            if channel != "global":
                recipients.update(self._subscriptions.get("global", set()))
            recipients_copy = set(recipients)
        disconnected: list = []
        sent = 0
        for ws in recipients_copy:
            if ws.client_state != WebSocketState.CONNECTED:
                disconnected.append(ws)
                continue
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as exc:
                logger.debug("Failed to send live event to client: %s", exc)
                disconnected.append(ws)
        for ws in disconnected:
            await self.remove_client(ws)
        logger.debug(
            "Published %s -> %s (event_id=%d, sent=%d)",
            event_type,
            channel,
            event_id,
            sent,
        )
        return sent


live_event_manager = LiveEventManager()


async def publish_live_event(channel: str, event_type: str, payload: dict) -> int:
    """Convenience helper to publish a scoped live event.

    Example:
        await publish_live_event("task:abc123", "task_progress", {"pct": 50})
        await publish_live_event("global", "cost_warning", {"threshold": 10.0})
    """
    return await live_event_manager.publish(channel, event_type, payload)
