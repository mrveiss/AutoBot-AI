# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Logger Plugin - Hook-Based Event Logging

Demonstrates hook system by logging agent and tool events.
Issue #730 - Plugin SDK example.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from plugin_sdk.base import BasePlugin, PluginManifest
from plugin_sdk.hooks import Hook, HookRegistry

logger = logging.getLogger(__name__)


class LoggerPlugin(BasePlugin):
    """Plugin that logs system events using hooks."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None):
        """Initialize logger plugin."""
        super().__init__(manifest, config)
        self.log_file = (
            Path(config.get("log_file", "/tmp/plugin_events.log"))
            if config
            else Path("/tmp/plugin_events.log")
        )
        self.hook_registry = HookRegistry()

    async def initialize(self) -> None:
        """Initialize plugin and register hooks."""
        self._logger.info("Logger Plugin initializing...")

        # Ensure log file exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.touch(exist_ok=True)

        # Register hooks
        self.hook_registry.register_hook(
            Hook.ON_AGENT_EXECUTE.value,
            self._log_agent_execute,
            plugin_name=self.manifest.name,
        )

        self.hook_registry.register_hook(
            Hook.ON_TOOL_CALL.value,
            self._log_tool_call,
            plugin_name=self.manifest.name,
        )

        self.hook_registry.register_hook(
            Hook.ON_MESSAGE_RECEIVED.value,
            self._log_message_received,
            plugin_name=self.manifest.name,
        )

        self._logger.info("Logger Plugin initialized - logging to %s", self.log_file)

    async def shutdown(self) -> None:
        """Clean up plugin and unregister hooks."""
        self._logger.info("Logger Plugin shutting down...")

        # Unregister all hooks for this plugin
        self.hook_registry.unregister_hook(
            Hook.ON_AGENT_EXECUTE.value, plugin_name=self.manifest.name
        )
        self.hook_registry.unregister_hook(
            Hook.ON_TOOL_CALL.value, plugin_name=self.manifest.name
        )
        self.hook_registry.unregister_hook(
            Hook.ON_MESSAGE_RECEIVED.value, plugin_name=self.manifest.name
        )

        self._logger.info("Logger Plugin shutdown complete")

    async def _log_agent_execute(self, agent_name: str, **kwargs: Any) -> None:
        """Log agent execution event."""
        self._write_log(
            {
                "event": "agent_execute",
                "agent_name": agent_name,
                "timestamp": datetime.now().isoformat(),
                "data": kwargs,
            }
        )

    async def _log_tool_call(self, tool_name: str, **kwargs: Any) -> None:
        """Log tool call event."""
        self._write_log(
            {
                "event": "tool_call",
                "tool_name": tool_name,
                "timestamp": datetime.now().isoformat(),
                "data": kwargs,
            }
        )

    async def _log_message_received(self, message: str, **kwargs: Any) -> None:
        """Log message received event."""
        self._write_log(
            {
                "event": "message_received",
                "message": message[:100],  # Truncate long messages
                "timestamp": datetime.now().isoformat(),
                "data": kwargs,
            }
        )

    def _write_log(self, data: Dict) -> None:
        """Write log entry to file."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data) + "\n")
        except Exception as e:
            self._logger.error("Failed to write log: %s", e)


# Export plugin class
Plugin = LoggerPlugin
