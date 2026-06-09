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

Migration plan:
  Phase 1 (this PR):   events/bus.py lands; agent_loop dual-publish fixed.
  Phase 2 (follow-up): Migrate api/workflow.py and top ~10 callers.
  Phase 3 (follow-up): Migrate remaining ~17 files, remove direct imports of
                        EventManager/LiveEventManager outside their modules.
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
    should use directly.  The bus handles the two lightweight in-memory managers
    whose split was causing the dual-publish workaround.
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
            # #8304: REDIS strategy has no implementation in this facade.
            # Callers needing durable Redis events must use RedisEventStreamManager
            # directly.  Log a critical error instead of silently dropping.
            logger.critical(
                "PersistStrategy.REDIS is not implemented in EventBus — event dropped "
                "(channel=%s, event_type=%s). Use RedisEventStreamManager directly.",
                channel,
                event_type,
            )
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

    def register_ws_broadcast(self, callback: Callable[[Dict[str, Any]], Awaitable[None]] | None) -> None:
        """Register (or clear) the EventManager WebSocket broadcast callback."""
        get_event_manager().register_websocket_broadcast(callback)


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
