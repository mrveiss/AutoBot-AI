# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# src/event_manager.py
import asyncio  # Added back asyncio import
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

import yaml
from constants.path_constants import PATH

logger = logging.getLogger(__name__)


class EventManager:
    """Manages event publishing and subscription with WebSocket support."""

    def __init__(self):
        """Initialize event manager with empty listeners and no WebSocket callback."""
        self._listeners: Dict[
            str, list[Callable[[Dict[str, Any]], Awaitable[None]]]
        ] = {}
        self._websocket_broadcast_callback: Optional[
            Callable[[Dict[str, Any]], Awaitable[None]]
        ] = None
        self._config = self._load_config()  # Load config on init

    def _load_config(self):
        """Load configuration from YAML file or return defaults."""
        # Use centralized PathConstants (Issue #380)
        config_path = PATH.CONFIG_DIR / "config.yaml"
        if not config_path.exists():
            logger.warning(
                f"Config file not found at {config_path}. "
                "Using default debug_mode=False."
            )
            return {"agent_behavior": {"debug_mode": False}}
        try:
            with open(str(config_path), "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(
                f"Error loading config file {config_path}: {e}. "
                "Using default debug_mode=False."
            )
            return {"agent_behavior": {"debug_mode": False}}

    def _is_debug_mode(self):
        """Check if debug mode is enabled in configuration."""
        return self._config.get("agent_behavior", {}).get("debug_mode", False)

    def register_websocket_broadcast(
        self, callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ):
        """Registers a callback function to broadcast events via WebSocket."""
        self._websocket_broadcast_callback = callback

    async def publish(self, event_type: str, payload: Dict[str, Any]):
        """Publishes an event to all registered listeners and broadcasts
        via WebSocket.
        """
        event_data = {"type": event_type, "payload": payload}

        # Broadcast via WebSocket if registered
        if self._websocket_broadcast_callback:
            await self._websocket_broadcast_callback(event_data)

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

    def subscribe(
        self, event_type: str, listener: Callable[[Dict[str, Any]], Awaitable[None]]
    ):
        """Subscribes a listener function to a specific event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def unsubscribe(
        self, event_type: str, listener: Callable[[Dict[str, Any]], Awaitable[None]]
    ):
        """Unsubscribes a listener function from a specific event type."""
        if event_type in self._listeners and listener in self._listeners[event_type]:
            self._listeners[event_type].remove(listener)


# Global instance of EventManager
event_manager = EventManager()

if __name__ == "__main__":

    async def test_listener(event):
        """Example listener that prints received event data."""
        print(f"Local Listener received: {event}")  # noqa: print

    async def main():
        """Main test function demonstrating EventManager usage."""
        event_manager.subscribe("task_update", test_listener)
        event_manager.subscribe("log_message", test_listener)

        # Simulate WebSocket broadcast callback
        async def mock_websocket_broadcast(event):
            """Mock callback that simulates WebSocket event broadcast."""
            print(f"WebSocket Broadcast: {event}")  # noqa: print

        event_manager.register_websocket_broadcast(mock_websocket_broadcast)

        await event_manager.publish(
            "task_update",
            {
                "task_id": "123",
                "status": "in_progress",
                "description": "Doing something",
            },
        )
        await event_manager.publish(
            "log_message", {"level": "INFO", "message": "Agent started."}
        )
        await event_manager.publish(
            "task_update",
            {
                "task_id": "123",
                "status": "completed",
                "description": "Finished something",
            },
        )

        # Test debug publish
        await event_manager.debug_publish(
            "debug_info", {"message": "This is a debug message."}
        )

    asyncio.run(main())
