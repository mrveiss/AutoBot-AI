# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin Hooks System

Event-based extensibility system allowing plugins to register callbacks
for system events.

Issue #730 - Plugin SDK for extensible tool architecture.
Issue #6970 - Hook registry with signatures and validation.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from enum import Enum
from typing import Any, Callable, Dict, List

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

    # Knowledge base hooks (Issue #3278)
    ON_KB_SEARCH = "on_kb_search"
    ON_KB_DOCUMENT_ADDED = "on_kb_document_added"
    ON_KB_DOCUMENT_REMOVED = "on_kb_document_removed"

    # Workflow hooks (Issue #3278)
    ON_WORKFLOW_START = "on_workflow_start"
    ON_WORKFLOW_COMPLETE = "on_workflow_complete"
    ON_WORKFLOW_ERROR = "on_workflow_error"

    # Custom hooks (plugins can define their own)
    CUSTOM = "custom"


class HookSignature:
    """Describes the expected keyword arguments for a hook."""

    def __init__(self, description: str, params: Dict[str, str]) -> None:
        self.description = description
        # Maps param name → type description string
        self.params = params

    def __repr__(self) -> str:
        return f"HookSignature({self.description!r}, params={list(self.params)})"


# Registry mapping canonical hook names to their expected signatures.
# Plugins declare hooks by name in PluginManifest.hooks; the loader
# validates each name against this registry and emits a DeprecationWarning
# for any name not found here.
HOOK_REGISTRY: Dict[str, HookSignature] = {
    Hook.ON_STARTUP.value: HookSignature(
        "Called once after all plugins are loaded.",
        {},
    ),
    Hook.ON_SHUTDOWN.value: HookSignature(
        "Called before the application shuts down.",
        {},
    ),
    Hook.ON_CONFIG_CHANGE.value: HookSignature(
        "Called when application configuration changes.",
        {"key": "str", "old_value": "Any", "new_value": "Any"},
    ),
    Hook.ON_AGENT_EXECUTE.value: HookSignature(
        "Called before an agent task is executed.",
        {"agent_id": "str", "task": "dict"},
    ),
    Hook.ON_AGENT_COMPLETE.value: HookSignature(
        "Called after an agent task completes.",
        {"agent_id": "str", "task": "dict", "result": "Any"},
    ),
    Hook.ON_AGENT_ERROR.value: HookSignature(
        "Called when an agent task raises an error.",
        {"agent_id": "str", "task": "dict", "error": "Exception"},
    ),
    Hook.ON_TOOL_CALL.value: HookSignature(
        "Called before a tool is invoked.",
        {"tool_name": "str", "args": "dict"},
    ),
    Hook.ON_TOOL_COMPLETE.value: HookSignature(
        "Called after a tool returns.",
        {"tool_name": "str", "args": "dict", "result": "Any"},
    ),
    Hook.ON_TOOL_ERROR.value: HookSignature(
        "Called when a tool raises an error.",
        {"tool_name": "str", "args": "dict", "error": "Exception"},
    ),
    Hook.ON_MESSAGE_RECEIVED.value: HookSignature(
        "Called when a chat message is received.",
        {"session_id": "str", "message": "str"},
    ),
    Hook.ON_MESSAGE_SENT.value: HookSignature(
        "Called when a chat message is sent.",
        {"session_id": "str", "message": "str"},
    ),
    Hook.ON_KB_SEARCH.value: HookSignature(
        "Called when the knowledge base is queried.",
        {"query": "str", "results": "list"},
    ),
    Hook.ON_KB_DOCUMENT_ADDED.value: HookSignature(
        "Called when a document is added to the knowledge base.",
        {"document_id": "str", "metadata": "dict"},
    ),
    Hook.ON_KB_DOCUMENT_REMOVED.value: HookSignature(
        "Called when a document is removed from the knowledge base.",
        {"document_id": "str"},
    ),
    Hook.ON_WORKFLOW_START.value: HookSignature(
        "Called when a workflow begins execution.",
        {"workflow_id": "str", "context": "dict"},
    ),
    Hook.ON_WORKFLOW_COMPLETE.value: HookSignature(
        "Called when a workflow finishes successfully.",
        {"workflow_id": "str", "result": "Any"},
    ),
    Hook.ON_WORKFLOW_ERROR.value: HookSignature(
        "Called when a workflow raises an error.",
        {"workflow_id": "str", "error": "Exception"},
    ),
    Hook.CUSTOM.value: HookSignature(
        "Generic custom hook for plugin-defined events.",
        {},
    ),
}


def validate_hook_names(hook_names: List[str], plugin_name: str = "unknown") -> None:
    """Emit a DeprecationWarning for any hook name not in HOOK_REGISTRY.

    Args:
        hook_names: Hook names declared in a plugin manifest.
        plugin_name: Plugin identifier, used in the warning message.
    """
    for name in hook_names:
        if name not in HOOK_REGISTRY:
            warnings.warn(
                f"Plugin '{plugin_name}' declares unknown hook '{name}'. "
                "This hook is not in HOOK_REGISTRY and may not be called. "
                "Use a name from plugin_sdk.hooks.Hook or register a custom "
                "hook in HOOK_REGISTRY before declaring it.",
                DeprecationWarning,
                stacklevel=2,
            )
            logger.warning(
                "Plugin '%s' declares unknown hook '%s' — not in HOOK_REGISTRY",
                plugin_name,
                name,
            )


class HookRegistry:
    """
    Singleton registry for managing hooks and callbacks.

    Allows plugins to register callbacks for system events.
    """

    _instance: "HookRegistry" | None = None
    _hooks: Dict[str, List[Any]] = {}  # Each entry is a dict with callback and plugin_name keys

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_hook(
        self,
        hook_name: str,
        callback: Callable,
        plugin_name: str | None = None,
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

    def unregister_hook(self, hook_name: str, plugin_name: str | None = None) -> None:
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
            self._hooks[hook_name] = [cb for cb in self._hooks[hook_name] if cb["plugin_name"] != plugin_name]
            logger.info("Unregistered hook '%s' for plugin '%s'", hook_name, plugin_name)
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
