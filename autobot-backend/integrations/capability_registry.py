# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Capability Registry for messaging and voice integrations (#11524).

Maps capability names to registered implementations. Consumers resolve by
capability, never by concrete class — eliminating vendor-branching.

Mirrors the credential-gated self-registration style of
``agent_loop.search.registry.SearchProviderRegistry``:

- Providers declare which capabilities they satisfy at registration time.
- Absent-capability queries return an empty list (never raise).
- Thread-safe singleton populated lazily on first use via
  ``get_capability_registry()``.

Usage::

    from integrations.capability_registry import MESSAGING, get_capability_registry

    registry = get_capability_registry()
    impls = registry.resolve(MESSAGING)
    if impls:
        await impls[0].send_message(channel_id, text)
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Well-known capability names — use these constants instead of bare strings.
MESSAGING = "messaging"
TTS = "tts"
STT = "stt"


class CapabilityRegistry:
    """Registry mapping capability names → ordered list of implementations.

    Registration order is preserved; first-registered is first-resolved.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._store: dict[str, list[Any]] = {}

    def register(self, capability: str, impl: Any) -> None:
        """Register *impl* under *capability*.

        Args:
            capability: Capability name constant (e.g. ``MESSAGING``).
            impl:       Any object satisfying the corresponding Protocol.
        """
        if capability not in self._store:
            self._store[capability] = []
        self._store[capability].append(impl)
        logger.debug(
            "Registered %s as capability=%s (total=%d)",
            type(impl).__name__,
            capability,
            len(self._store[capability]),
        )

    def resolve(self, capability: str) -> list[Any]:
        """Return all registered implementations for *capability*.

        Returns an empty list (never raises) when capability is absent.

        Args:
            capability: Capability name to look up.
        """
        return list(self._store.get(capability, []))

    def capabilities(self) -> list[str]:
        """Return registered capability names in insertion order."""
        return list(self._store.keys())


_registry: CapabilityRegistry | None = None
_registry_lock = threading.Lock()


def _populate_default_providers(registry: CapabilityRegistry) -> None:
    """Credential-gate integration registrations from ssot_config (#11524).

    Mirrors the pattern in ``agent_loop.search.registry._populate_default_providers``:
    import lazily, skip silently when credentials are absent.
    """
    try:
        from autobot_shared.ssot_config import config as _cfg
    except Exception as exc:  # ssot_config unavailable in test environments
        logger.debug("ssot_config unavailable — skipping default capability registrations: %s", exc)
        return

    # --- Messaging: Slack ---
    slack_token = getattr(_cfg, "slack_bot_token", "") or ""
    if slack_token:
        try:
            from integrations.base import IntegrationConfig
            from integrations.communication_integration import SlackIntegration
            from integrations.messaging_adapters import SlackMessagingAdapter

            slack_cfg = IntegrationConfig(name="slack", provider="slack", token=slack_token)
            registry.register(MESSAGING, SlackMessagingAdapter(SlackIntegration(slack_cfg)))
            logger.debug("Registered SlackMessagingAdapter for capability=%s", MESSAGING)
        except Exception as exc:
            logger.warning("Failed to register Slack messaging capability: %s", exc)
    else:
        logger.debug("SLACK_BOT_TOKEN not set — Slack messaging capability not registered")

    # --- Messaging: Discord ---
    discord_token = getattr(_cfg, "discord_bot_token", "") or ""
    if discord_token:
        try:
            from integrations.base import IntegrationConfig
            from integrations.communication_integration import DiscordIntegration
            from integrations.messaging_adapters import DiscordMessagingAdapter

            discord_cfg = IntegrationConfig(name="discord", provider="discord", token=discord_token)
            registry.register(MESSAGING, DiscordMessagingAdapter(DiscordIntegration(discord_cfg)))
            logger.debug("Registered DiscordMessagingAdapter for capability=%s", MESSAGING)
        except Exception as exc:
            logger.warning("Failed to register Discord messaging capability: %s", exc)
    else:
        logger.debug("DISCORD_BOT_TOKEN not set — Discord messaging capability not registered")

    # --- TTS ---
    try:
        from services.tts_client import get_tts_client

        registry.register(TTS, get_tts_client())
        logger.debug("Registered TTSClient for capability=%s", TTS)
    except Exception as exc:
        logger.warning("Failed to register TTS capability: %s", exc)


def get_capability_registry() -> CapabilityRegistry:
    """Return the process-wide registry, populating it lazily on first use."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                registry = CapabilityRegistry()
                try:
                    _populate_default_providers(registry)
                except Exception as exc:
                    logger.warning("Capability registry auto-registration failed: %s", exc)
                _registry = registry
    return _registry
