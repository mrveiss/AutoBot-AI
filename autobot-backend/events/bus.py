# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unified event bus facade (#6486).

Three parallel event systems coexisted (EventManager, LiveEventManager,
RedisEventStreamManager) with callers forced to publish to multiple buses
to reach all subscribers.  The smoking gun: agent_loop/loop.py lines 879-895
explicitly published to both EventManager and LiveEventManager to bridge the
gap.

This facade is the single publish/subscribe entry-point.  Internally it fans
out to the appropriate backend(s) based on ``persist``.  The three underlying
managers are preserved; this layer simply removes the need for callers to know
which combination to invoke.

The governing rules for this layer — principles, design tests and anti-goals —
live in ``docs/developer/EVENT_STATE_DOCTRINE.md`` (#14823).  Read that before
adding a fourth bus, a new WebSocket route, or an event type that is only ever
delivered as an ephemeral notification.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Awaitable, Callable, Dict

from fastapi import WebSocket

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from event_manager import get_event_manager
from live_event_manager import get_live_event_manager

logger = get_logger(__name__)


class PersistStrategy(Enum):
    """Controls which storage backend(s) receive the event."""

    NONE = "none"  # In-memory EventManager only (fire-and-forget signals)
    MEMORY = "memory"  # LiveEventManager (WebSocket fan-out, channel-scoped)
    BOTH = "both"  # EventManager + LiveEventManager (old workaround, now explicit)
    REDIS = "redis"  # RedisEventStreamManager (durable, task-scoped history)


class EventBus:
    """Single facade over EventManager + LiveEventManager.

    RedisEventStreamManager is intentionally NOT wrapped here — it has a
    richer typed API (AgentEvent dataclasses, task-scoped streams) that callers
    should use directly.  ``PersistStrategy.REDIS`` instead durably records the
    *channel* event stream via ``ChannelEventStream`` (#14816), which is what
    reconnect-with-replay reads back (#14818).
    """

    async def publish(
        self,
        channel: str,
        event_type: str,
        payload: Dict[str, Any],
        *,
        persist: PersistStrategy = PersistStrategy.MEMORY,
    ) -> None:
        """Publish an event.

        Args:
            channel: Channel name (``agent:{id}``, ``task:{id}``, ``global``,
                     or a legacy EventManager event type string).
            event_type: Event type string.
            payload: Event payload dict.
            persist: Which backend(s) receive the event.
        """
        if persist is PersistStrategy.REDIS:
            # #14816: previously this logged critical and dropped the event.
            # A durable publish now goes through the same channel fan-out as
            # MEMORY — a persisted event no connected client sees would be a
            # regression on the old behaviour — and additionally lands in the
            # channel's Redis replay window.
            await get_live_event_manager().publish(channel, event_type, payload, durable=True)
            return
        if persist in (PersistStrategy.NONE, PersistStrategy.BOTH):
            await get_event_manager().publish(event_type, {"channel": channel, **payload})
        if persist in (PersistStrategy.MEMORY, PersistStrategy.BOTH):
            await get_live_event_manager().publish(channel, event_type, payload)

    async def subscribe_ws(self, ws: WebSocket, channel: str) -> bool:
        """Subscribe a WebSocket client to a channel in LiveEventManager."""
        return await get_live_event_manager().subscribe(ws, channel)

    async def unsubscribe_ws(self, ws: WebSocket, channel: str) -> None:
        """Unsubscribe a WebSocket client from a channel."""
        await get_live_event_manager().unsubscribe(ws, channel)

    async def remove_client(self, ws: WebSocket) -> None:
        """Remove a disconnected client from all LiveEventManager channels."""
        await get_live_event_manager().remove_client(ws)

    def subscribe(self, event_type: str, listener: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Subscribe a listener to EventManager events (in-process signals)."""
        get_event_manager().subscribe(event_type, listener)

    def unsubscribe(self, event_type: str, listener: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Unsubscribe a listener from EventManager events."""
        get_event_manager().unsubscribe(event_type, listener)

    def register_ws_broadcast(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Register one connection's EventManager WebSocket broadcast callback (#14814)."""
        get_event_manager().register_websocket_broadcast(callback)

    def unregister_ws_broadcast(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Unregister one connection's broadcast callback, leaving others intact (#14814)."""
        get_event_manager().unregister_websocket_broadcast(callback)

    def register_persistence_hook(self, hook: Callable[[Dict[str, Any]], Awaitable[None]] | None) -> None:
        """Register the hook that durably records every published event (#14814)."""
        get_event_manager().register_persistence_hook(hook)


get_event_bus = lazy_singleton(EventBus)


# ---------------------------------------------------------------------------
# Convenience re-exports so callers can drop-in replace publish_live_event
# ---------------------------------------------------------------------------


async def publish_event(
    channel: str,
    event_type: str,
    payload: Dict[str, Any],
    *,
    persist: PersistStrategy = PersistStrategy.MEMORY,
) -> None:
    """Module-level convenience wrapper around :func:`EventBus.publish`."""
    await get_event_bus().publish(channel, event_type, payload, persist=persist)
