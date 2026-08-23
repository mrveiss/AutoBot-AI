# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Live Event Manager - Scoped Real-Time Events (#1408)

In-memory channel router for WebSocket-based entity-scoped event streaming.
Supports channels: agent:{id}, task:{id}, workflow:{id}, heartbeat:{id}, global
"""

import asyncio
from typing import Dict, Set

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from events.channel_stream import get_channel_event_stream

logger = get_logger(__name__)

# #14819: session and chat make a conversation addressable, which is what lets
# several clients subscribe to the same conversation instead of falling back to
# ``global`` (everything) or the legacy single-client endpoint.
_VALID_PREFIXES = {
    "agent",
    "task",
    "workflow",
    "heartbeat",
    "company",
    "board",
    "session",
    "chat",
}


def _is_valid_channel(channel: str) -> bool:
    """Return True for a valid channel — a known ``{prefix}:{id}`` form, or ``global``."""
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

    async def publish(self, channel: str, event_type: str, payload: dict, *, durable: bool = False) -> int:
        """Publish event to channel subscribers and global subscribers.

        #14817: the sequence number comes from :class:`ChannelEventStream`
        (Redis ``INCR``), so it is monotonic across restarts and shared between
        workers.  It previously came from a process-local dict, which reset on
        restart and diverged across processes — an id a client trusts but which
        silently restarts is worse than no id at all.

        ``durable`` additionally records the event in the channel's replay
        window so a reconnecting client can ask for what it missed (#14818).
        """
        if not _is_valid_channel(channel):
            logger.warning("Publish to invalid channel ignored: %s", channel)
            return 0
        event_id = await get_channel_event_stream().next_event_id(channel)
        message = {
            "type": "live_event",
            "channel": channel,
            "event_type": event_type,
            "event_id": event_id,
            "payload": payload,
        }
        if durable:
            await get_channel_event_stream().append(channel, message)
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


get_live_event_manager = lazy_singleton(LiveEventManager)


async def publish_live_event(channel: str, event_type: str, payload: dict) -> int:
    """Convenience helper to publish a scoped live event.

    Example:
        await publish_live_event("task:abc123", "task_progress", {"pct": 50})
        await publish_live_event("global", "cost_warning", {"threshold": 10.0})
    """
    return await get_live_event_manager().publish(channel, event_type, payload)
