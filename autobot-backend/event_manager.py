# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# src/event_manager.py
"""
Async event pub/sub manager for cross-component signalling.

Publishes named events to all registered async callbacks; supports
both fire-and-forget and awaitable delivery patterns.
"""

import asyncio  # Added back asyncio import
from typing import Any, Awaitable, Callable, Dict, Set

import yaml

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from constants.path_constants import PATH

logger = get_logger(__name__)


class EventManager:
    """Manages event publishing and subscription with WebSocket support."""

    def __init__(self):
        """Initialize event manager with empty listeners and no WebSocket callbacks."""
        self._listeners: Dict[str, list[Callable[[Dict[str, Any]], Awaitable[None]]]] = {}
        # #14814: a set, not a scalar.  This was a single callback, so each new
        # WebSocket connection overwrote the previous one and the first
        # disconnect cleared delivery for everyone still connected.
        self._websocket_broadcast_callbacks: Set[Callable[[Dict[str, Any]], Awaitable[None]]] = set()
        # #14814: persistence must not be a side effect of delivery.  This hook
        # fires exactly once per publish, whether zero clients or ten are
        # connected.
        self._persistence_hook: Callable[[Dict[str, Any]], Awaitable[None]] | None = None
        self._config = self._load_config()  # Load config on init

    def _load_config(self):
        """Load configuration from YAML file or return defaults."""
        # Use centralized PathConstants (Issue #380)
        config_path = PATH.CONFIG_DIR / "config.yaml"
        if not config_path.exists():
            logger.warning(f"Config file not found at {config_path}. " "Using default debug_mode=False.")
            return {"agent_behavior": {"debug_mode": False}}
        try:
            with open(str(config_path), "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config file {config_path}: {e}. " "Using default debug_mode=False.")
            return {"agent_behavior": {"debug_mode": False}}

    def _is_debug_mode(self):
        """Check if debug mode is enabled in configuration."""
        return self._config.get("agent_behavior", {}).get("debug_mode", False)

    def register_websocket_broadcast(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Register one connection's broadcast callback.

        #14814: additive.  Every connected client keeps receiving events when
        another connects or drops; pair each call with
        :meth:`unregister_websocket_broadcast`.
        """
        if callback is None:
            raise ValueError("callback must not be None — use unregister_websocket_broadcast()")
        self._websocket_broadcast_callbacks.add(callback)

    def unregister_websocket_broadcast(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Remove one connection's broadcast callback, leaving the others intact."""
        self._websocket_broadcast_callbacks.discard(callback)

    def register_persistence_hook(self, hook: Callable[[Dict[str, Any]], Awaitable[None]] | None) -> None:
        """Register the single hook that durably records published events.

        #14814: chat history used to be written from inside the WebSocket
        broadcast callback, so with no client attached nothing was persisted at
        all.  Persistence now hangs here instead, decoupled from delivery.
        """
        self._persistence_hook = hook

    @property
    def websocket_broadcast_count(self) -> int:
        """Number of registered broadcast callbacks (used by tests and diagnostics)."""
        return len(self._websocket_broadcast_callbacks)

    async def publish(self, event_type: str, payload: Dict[str, Any]):
        """Publishes an event to all registered listeners and broadcasts
        via WebSocket.
        """
        event_data = {"type": event_type, "payload": payload}

        # #14814: persist first and exactly once, independent of how many
        # clients are attached.  A persistence failure must not stop delivery.
        if self._persistence_hook is not None:
            try:
                await self._persistence_hook(event_data)
            except Exception as exc:
                logger.error("Event persistence hook failed: %s", exc)

        # #14814: fan out to every registered connection.  Iterate a copy — a
        # failing callback is removed mid-loop.  One dead socket must not stop
        # delivery to the others, so each is isolated.
        for callback in list(self._websocket_broadcast_callbacks):
            try:
                await callback(event_data)
            except Exception as exc:
                logger.warning("WebSocket broadcast callback failed, unregistering: %s", exc)
                self._websocket_broadcast_callbacks.discard(callback)

        # Notify local listeners (if any)
        if event_type in self._listeners:
            for listener in self._listeners[event_type]:
                # Run listeners in a non-blocking way if they are async
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(event_data))
                else:
                    listener(event_data)

    async def debug_publish(self, event_type: str, payload: Dict[str, Any]):
        """Publishes an event only if debug mode is enabled."""
        if self._is_debug_mode():
            await self.publish(event_type, payload)
        else:
            logger.debug("Debug event '%s' not published (debug mode off).", event_type)

    def subscribe(self, event_type: str, listener: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Subscribes a listener function to a specific event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: str, listener: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Unsubscribes a listener function from a specific event type."""
        if event_type in self._listeners and listener in self._listeners[event_type]:
            self._listeners[event_type].remove(listener)


get_event_manager = lazy_singleton(EventManager)

if __name__ == "__main__":

    async def test_listener(event):
        """Example listener that prints received event data."""
        logger.info("Local Listener received: %s", event)

    async def main():
        """Main test function demonstrating EventManager usage."""
        get_event_manager().subscribe("task_update", test_listener)
        get_event_manager().subscribe("log_message", test_listener)

        # Simulate WebSocket broadcast callback
        async def mock_websocket_broadcast(event):
            """Mock callback that simulates WebSocket event broadcast."""
            logger.info("WebSocket Broadcast: %s", event)

        get_event_manager().register_websocket_broadcast(mock_websocket_broadcast)

        await get_event_manager().publish(
            "task_update",
            {
                "task_id": "123",
                "status": "in_progress",
                "description": "Doing something",
            },
        )
        await get_event_manager().publish("log_message", {"level": "INFO", "message": "Agent started."})
        await get_event_manager().publish(
            "task_update",
            {
                "task_id": "123",
                "status": "completed",
                "description": "Finished something",
            },
        )

        # Test debug publish
        await get_event_manager().debug_publish("debug_info", {"message": "This is a debug message."})

    run_or_schedule(main())
