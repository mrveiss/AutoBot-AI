# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
KB Event Plugin - Example Hook-Based Integration

Demonstrates how a third-party plugin hooks into AutoBot's chat workflow and
knowledge base events.  Ships as part of the plugin SDK documentation.

Hooks used:
    ON_MESSAGE_RECEIVED - fires when a user message enters the chat workflow
    ON_KB_SEARCH        - fires after an agentic knowledge-base search
    ON_AGENT_COMPLETE   - fires after each LLM iteration completes

Issue #3278 - Plugin and extension system for third-party integrations.
"""

import logging
from typing import Any, Dict, Optional

from plugin_sdk.base import BasePlugin, PluginManifest
from plugin_sdk.hooks import Hook, HookRegistry

logger = logging.getLogger(__name__)


class KbEventPlugin(BasePlugin):
    """Plugin that records chat and knowledge base events for audit/analytics."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None) -> None:
        super().__init__(manifest, config)
        self._log_messages: bool = (config or {}).get("log_messages", True)
        self._log_kb_searches: bool = (config or {}).get("log_kb_searches", True)
        self._hook_registry = HookRegistry()
        self._event_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Register hooks on startup."""
        self._logger.info("KbEventPlugin: initializing")

        if self._log_messages:
            self._hook_registry.register_hook(
                Hook.ON_MESSAGE_RECEIVED.value,
                self._on_message_received,
                plugin_name=self.manifest.name,
            )

        if self._log_kb_searches:
            self._hook_registry.register_hook(
                Hook.ON_KB_SEARCH.value,
                self._on_kb_search,
                plugin_name=self.manifest.name,
            )

        self._hook_registry.register_hook(
            Hook.ON_AGENT_COMPLETE.value,
            self._on_agent_complete,
            plugin_name=self.manifest.name,
        )

        self._logger.info("KbEventPlugin: registered hooks — ready")

    async def shutdown(self) -> None:
        """Unregister hooks on shutdown."""
        self._logger.info("KbEventPlugin: shutting down (event_counts=%s)", self._event_counts)

        for hook in [
            Hook.ON_MESSAGE_RECEIVED.value,
            Hook.ON_KB_SEARCH.value,
            Hook.ON_AGENT_COMPLETE.value,
        ]:
            self._hook_registry.unregister_hook(hook, plugin_name=self.manifest.name)

    # ------------------------------------------------------------------
    # Hook callbacks
    # ------------------------------------------------------------------

    async def _on_message_received(self, *, session_id: str, message: str, **_: Any) -> None:
        """Audit-log incoming chat messages."""
        self._event_counts["on_message_received"] = self._event_counts.get("on_message_received", 0) + 1
        self._logger.info(
            "KbEventPlugin[on_message_received] session=%s message_len=%d",
            session_id,
            len(message),
        )

    async def _on_kb_search(self, *, session_id: str, query: str, context_length: int, **_: Any) -> None:
        """Audit-log knowledge base searches."""
        self._event_counts["on_kb_search"] = self._event_counts.get("on_kb_search", 0) + 1
        self._logger.info(
            "KbEventPlugin[on_kb_search] session=%s query_len=%d context_len=%d",
            session_id,
            len(query),
            context_length,
        )

    async def _on_agent_complete(self, *, session_id: str, iteration: int, response: str, **_: Any) -> None:
        """Audit-log completed agent (LLM) iterations."""
        self._event_counts["on_agent_complete"] = self._event_counts.get("on_agent_complete", 0) + 1
        self._logger.info(
            "KbEventPlugin[on_agent_complete] session=%s iteration=%d response_len=%d",
            session_id,
            iteration,
            len(response),
        )

    # ------------------------------------------------------------------
    # Public helpers (for testing / API access)
    # ------------------------------------------------------------------

    def get_event_counts(self) -> Dict[str, int]:
        """Return accumulated event counts since plugin was initialized."""
        return dict(self._event_counts)


# Required: entry point used by PluginLoader
Plugin = KbEventPlugin
