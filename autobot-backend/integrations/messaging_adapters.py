# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Thin MessagingProtocol adapters for Slack and Discord (#11524).

Each adapter wraps a concrete integration instance and maps the
``MessagingProtocol`` surface (``send_message`` / ``fetch_messages``)
onto the underlying integration's ``execute_action`` calls.

No behaviour is changed in the underlying integrations; adapters only
translate method-name differences. These classes satisfy
``isinstance(obj, MessagingProtocol)`` at runtime.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from integrations.protocols import MessagingProtocol

if TYPE_CHECKING:
    from integrations.communication_integration import DiscordIntegration, SlackIntegration

logger = logging.getLogger(__name__)


class SlackMessagingAdapter:
    """Adapts ``SlackIntegration`` to satisfy ``MessagingProtocol``.

    Maps:
    - ``send_message``   → ``execute_action("send_message", ...)``
    - ``fetch_messages`` → ``execute_action("get_channel_history", ...)``
    """

    def __init__(self, integration: SlackIntegration) -> None:
        self._integration = integration

    async def send_message(self, channel_id: str, text: str, **kwargs) -> dict:
        """Send *text* to Slack channel *channel_id*.

        Extra kwargs (e.g. ``blocks``) are forwarded as-is to the action params.
        """
        params: dict = {"channel": channel_id, "text": text, **kwargs}
        return await self._integration.execute_action("send_message", params)

    async def fetch_messages(self, channel_id: str, limit: int = 100) -> list[dict]:
        """Fetch up to *limit* messages from Slack channel *channel_id*."""
        result = await self._integration.execute_action(
            "get_channel_history",
            {"channel": channel_id, "limit": limit},
        )
        messages = result.get("messages", [])
        if not isinstance(messages, list):
            logger.warning("SlackMessagingAdapter.fetch_messages: unexpected payload shape")
            return []
        return messages


class DiscordMessagingAdapter:
    """Adapts ``DiscordIntegration`` to satisfy ``MessagingProtocol``.

    Maps:
    - ``send_message``   → ``execute_action("send_message", ...)``
    - ``fetch_messages`` → Discord has no native history action in the current
                           integration; returns ``[]`` and logs a debug note.
    """

    def __init__(self, integration: DiscordIntegration) -> None:
        self._integration = integration

    async def send_message(self, channel_id: str, text: str, **kwargs) -> dict:
        """Send *text* to Discord channel *channel_id*.

        Discord's action uses ``content`` instead of ``text``; the adapter
        bridges the naming difference.
        """
        params: dict = {"channel_id": channel_id, "content": text, **kwargs}
        return await self._integration.execute_action("send_message", params)

    async def fetch_messages(self, channel_id: str, limit: int = 100) -> list[dict]:
        """Return message history for Discord channel *channel_id*.

        The current DiscordIntegration does not expose a ``get_channel_history``
        action, so this method returns an empty list. The Discord REST endpoint
        ``GET /channels/{id}/messages`` can be added to DiscordIntegration in a
        follow-up without changing this Protocol surface.
        """
        logger.debug(
            "DiscordMessagingAdapter.fetch_messages: fetch not yet implemented "
            "(channel_id=%s, limit=%d)",
            channel_id,
            limit,
        )
        return []


# Static structural assertion — checked at import time, not at runtime:
# ensures both adapter classes satisfy MessagingProtocol without needing
# to subclass it.
assert issubclass(SlackMessagingAdapter, MessagingProtocol), (
    "SlackMessagingAdapter does not satisfy MessagingProtocol"
)
assert issubclass(DiscordMessagingAdapter, MessagingProtocol), (
    "DiscordMessagingAdapter does not satisfy MessagingProtocol"
)
