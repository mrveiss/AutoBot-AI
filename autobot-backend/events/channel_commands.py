# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Client-to-server command dispatch on the channel socket (#14824).

Consolidating the bespoke WebSocket routes onto channel subscriptions ran into a
gap: ``/ws/live`` only ever accepted ``subscribe``, ``unsubscribe`` and
``ping``.  Eight of the nine routes queued for migration are **bidirectional** —
the client sends commands (start a research run, pause an operation, change a
metrics interval) — and there was nowhere for those to go.  Without this, a
migrated route would lose half its behaviour.

The design mirrors subscription: a command is addressed to a ``channel``, and
the handler registered for that channel's prefix serves it.  That keeps one
routing rule for the whole socket — dispatch on ``(action, channel)`` — instead
of reintroducing per-route knowledge in the endpoint.

Authorization is deliberately **not** re-implemented here.  The caller passes an
``authorize`` callable and dispatch refuses to run a handler without it, so a
command can never reach a channel the caller could not subscribe to.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

# A handler receives (channel, command, payload, user_payload) and returns an
# optional result dict sent back to the caller.
CommandHandler = Callable[[str, str, Dict[str, Any], Optional[Dict[str, Any]]], Awaitable[Optional[Dict[str, Any]]]]


class ChannelCommandRegistry:
    """Maps a channel prefix to the handler that serves its commands."""

    def __init__(self) -> None:
        self._handlers: Dict[str, CommandHandler] = {}

    def register(self, prefix: str, handler: CommandHandler) -> None:
        """Register the handler for one channel prefix (``research``, ``operation``, ...)."""
        if prefix in self._handlers:
            # Replacing silently would make two features fight over a prefix
            # with the winner decided by import order.
            logger.warning("Replacing existing command handler for prefix: %s", prefix)
        self._handlers[prefix] = handler
        logger.debug("Registered channel command handler for prefix: %s", prefix)

    def unregister(self, prefix: str) -> None:
        """Remove a prefix's handler."""
        self._handlers.pop(prefix, None)

    def handler_for(self, channel: str) -> CommandHandler | None:
        """Return the handler serving ``channel``, or None."""
        prefix, _, _ident = channel.partition(":")
        return self._handlers.get(prefix or channel)

    @property
    def prefixes(self) -> set[str]:
        """Prefixes with a registered handler (used by tests and diagnostics)."""
        return set(self._handlers)


get_channel_command_registry = lazy_singleton(ChannelCommandRegistry)


class CommandRefused(Exception):
    """A command could not be served.  Carries a client-safe reason."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def dispatch_command(
    channel: str,
    command: str,
    payload: Dict[str, Any],
    user_payload: Optional[Dict[str, Any]],
    authorize: Callable[[str, Optional[Dict[str, Any]]], Awaitable[bool]],
) -> Optional[Dict[str, Any]]:
    """Authorize and run one channel command.

    Raises :class:`CommandRefused` for every rejection path — unknown channel,
    unauthorized caller, missing handler — so the endpoint has one place to
    translate a refusal into an error frame, and no refusal can be mistaken for
    a successful no-op.
    """
    if not channel or not command:
        raise CommandRefused("channel and command are required")

    # Authorize before looking up the handler: whether a handler exists is
    # itself information about what the deployment runs.
    if not await authorize(channel, user_payload):
        raise CommandRefused(f"Not authorized for {channel}")

    handler = get_channel_command_registry().handler_for(channel)
    if handler is None:
        raise CommandRefused(f"No command handler for {channel}")

    try:
        return await handler(channel, command, payload or {}, user_payload)
    except CommandRefused:
        raise
    except Exception as exc:
        logger.exception("Channel command %s failed on %s", command, channel)
        raise CommandRefused(f"Command failed: {exc}")
