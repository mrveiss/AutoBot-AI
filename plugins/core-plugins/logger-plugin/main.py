# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Logger Plugin - Hook-Based Event Logging

Demonstrates hook system by logging agent and tool events.
Issue #730 - Plugin SDK example.
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from plugin_sdk.base import BasePlugin, PluginManifest
from plugin_sdk.hooks import Hook, HookRegistry

logger = logging.getLogger(__name__)


def _default_log_path() -> Path:
    """Per-deployment log path, never a shared /tmp name (#13967)."""
    base = os.environ.get("AUTOBOT_LOG_DIR")
    if base:
        return Path(base) / "plugin_events.log"
    return Path(tempfile.gettempdir()) / f"autobot-plugins-{os.getuid()}" / "plugin_events.log"


class LoggerPlugin(BasePlugin):
    """Plugin that logs system events using hooks."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None):
        """Initialize logger plugin."""
        super().__init__(manifest, config)
        # #13967: `/tmp/plugin_events.log` is a fixed name in a world-writable
        # directory, so the first user to create it owns it and every other user
        # gets PermissionError. Default under the project's log directory, which
        # is per-deployment and matches what the rest of the repo does; the
        # manifest's config_schema still allows an override.
        self.log_file = Path((config or {}).get("log_file") or _default_log_path())
        self.hook_registry = HookRegistry()
        # False until initialize() proves the sink opened. Defaulting to True
        # would let an uninitialised instance write and fail per event.
        self._sink_enabled = False

    async def initialize(self) -> None:
        """Initialize plugin and register hooks."""
        self._logger.info("Logger Plugin initializing...")

        # #13967: degrade, do not die. An environment condition took the whole
        # plugin down — and a logging plugin that cannot open its log file is
        # not a reason to have no plugin. The failure names the path so the
        # cause is actionable rather than a bare PermissionError at import time.
        self._sink_enabled = True
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.touch(exist_ok=True)
        except OSError as exc:
            self._sink_enabled = False
            self._logger.warning(
                "Logger Plugin: file sink disabled — cannot open %s (%s). "
                "Events will still reach the application log.",
                self.log_file,
                exc,
            )

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
        self.hook_registry.unregister_hook(Hook.ON_AGENT_EXECUTE.value, plugin_name=self.manifest.name)
        self.hook_registry.unregister_hook(Hook.ON_TOOL_CALL.value, plugin_name=self.manifest.name)
        self.hook_registry.unregister_hook(Hook.ON_MESSAGE_RECEIVED.value, plugin_name=self.manifest.name)

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
        """Write log entry to file, if the sink came up (#13967)."""
        if not self._sink_enabled:
            # Already reported once at initialize(); re-reporting per event
            # would turn a degraded sink into a log flood.
            return
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data) + "\n")
        except Exception as e:
            self._logger.error("Failed to write log: %s", e)


# Export plugin class
Plugin = LoggerPlugin
