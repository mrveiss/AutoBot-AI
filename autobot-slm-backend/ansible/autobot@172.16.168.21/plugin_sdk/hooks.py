# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin Hooks System

Event-based extensibility system allowing plugins to register callbacks
for system events.

Issue #730 - Plugin SDK for extensible tool architecture.
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Hook(str, Enum):
    """Pre-defined system hooks."""

    # System lifecycle hooks
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_CONFIG_CHANGE = "on_config_change"

    # Agent execution hooks
    ON_AGENT_EXECUTE = "on_agent_execute"
    ON_AGENT_COMPLETE = "on_agent_complete"
    ON_AGENT_ERROR = "on_agent_error"

    # Tool execution hooks
    ON_TOOL_CALL = "on_tool_call"
    ON_TOOL_COMPLETE = "on_tool_complete"
    ON_TOOL_ERROR = "on_tool_error"

    # Chat hooks
    ON_MESSAGE_RECEIVED = "on_message_received"
    ON_MESSAGE_SENT = "on_message_sent"

    # Custom hooks (plugins can define their own)
    CUSTOM = "custom"


class HookRegistry:
    """
    Singleton registry for managing hooks and callbacks.

    Allows plugins to register callbacks for system events.
    """

    _instance: Optional["HookRegistry"] = None
    _hooks: Dict[str, List[Callable]] = {}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_hook(
        self,
        hook_name: str,
        callback: Callable,
        plugin_name: Optional[str] = None,
    ) -> None:
        """
        Register a callback for a hook.

        Args:
            hook_name: Hook name (use Hook enum values)
            callback: Async or sync callable
            plugin_name: Plugin name for tracking (optional)
        """
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []

        # Store callback with metadata
        callback_info = {
            "callback": callback,
            "plugin_name": plugin_name,
        }
        self._hooks[hook_name].append(callback_info)

        logger.info(
            "Registered hook '%s' for plugin '%s'",
            hook_name,
            plugin_name or "unknown",
        )

    def unregister_hook(
        self, hook_name: str, plugin_name: Optional[str] = None
    ) -> None:
        """
        Unregister callbacks for a hook.

        Args:
            hook_name: Hook name
            plugin_name: If provided, only unregister callbacks from this plugin
        """
        if hook_name not in self._hooks:
            return

        if plugin_name:
            # Remove only callbacks from specified plugin
            self._hooks[hook_name] = [
                cb for cb in self._hooks[hook_name] if cb["plugin_name"] != plugin_name
            ]
            logger.info(
                "Unregistered hook '%s' for plugin '%s'", hook_name, plugin_name
            )
        else:
            # Remove all callbacks
            del self._hooks[hook_name]
            logger.info("Unregistered all callbacks for hook '%s'", hook_name)

    async def call_hook(
        self,
        hook_name: str,
        *args,
        **kwargs,
    ) -> List[Any]:
        """
        Call all callbacks registered for a hook.

        Args:
            hook_name: Hook name
            *args: Positional arguments to pass to callbacks
            **kwargs: Keyword arguments to pass to callbacks

        Returns:
            List of results from all callbacks
        """
        if hook_name not in self._hooks:
            return []

        results = []
        for callback_info in self._hooks[hook_name]:
            callback = callback_info["callback"]
            plugin_name = callback_info["plugin_name"]

            try:
                # Handle both async and sync callbacks
                if asyncio.iscoroutinefunction(callback):
                    result = await callback(*args, **kwargs)
                else:
                    result = callback(*args, **kwargs)

                results.append(result)

            except Exception as e:
                logger.error(
                    "Error calling hook '%s' for plugin '%s': %s",
                    hook_name,
                    plugin_name or "unknown",
                    e,
                    exc_info=True,
                )

        logger.debug("Called hook '%s' with %d callbacks", hook_name, len(results))
        return results

    def get_hook_count(self, hook_name: str) -> int:
        """Get number of callbacks registered for a hook."""
        return len(self._hooks.get(hook_name, []))

    def get_all_hooks(self) -> Dict[str, int]:
        """Get all registered hooks with callback counts."""
        return {hook: len(callbacks) for hook, callbacks in self._hooks.items()}

    def clear(self) -> None:
        """Clear all registered hooks."""
        self._hooks.clear()
        logger.info("Cleared hook registry")
