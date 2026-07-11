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


def _register_messaging_if_token(
    registry: CapabilityRegistry,
    provider: str,
    token: str,
    integration_cls,
    adapter_cls,
) -> None:
    """Register one messaging adapter when its bot token is configured."""
    if not token:
        logger.debug("%s bot token not set — messaging capability not registered", provider)
        return
    try:
        from integrations.base import IntegrationConfig

        cfg = IntegrationConfig(name=provider, provider=provider, token=token)
        registry.register(MESSAGING, adapter_cls(integration_cls(cfg)))
        logger.debug("Registered %s adapter for capability=%s", provider, MESSAGING)
    except Exception as exc:
        logger.warning("Failed to register %s messaging capability: %s", provider, exc)


def _populate_default_providers(registry: CapabilityRegistry) -> None:
    """Credential-gate integration registrations from ssot_config (#11524).

    Mirrors ``agent_loop.search.registry``: import lazily, skip silently when
    credentials are absent.
    """
    try:
        from autobot_shared.ssot_config import config as _cfg
    except Exception as exc:  # ssot_config unavailable in test environments
        logger.debug("ssot_config unavailable — skipping default capability registrations: %s", exc)
        return

    from integrations.communication_integration import DiscordIntegration, SlackIntegration
    from integrations.messaging_adapters import DiscordMessagingAdapter, SlackMessagingAdapter

    slack_token = getattr(_cfg, "slack_bot_token", "") or ""
    _register_messaging_if_token(registry, "slack", slack_token, SlackIntegration, SlackMessagingAdapter)
    discord_token = getattr(_cfg, "discord_bot_token", "") or ""
    _register_messaging_if_token(registry, "discord", discord_token, DiscordIntegration, DiscordMessagingAdapter)

    try:
        from services.tts_client import get_tts_client

        registry.register(TTS, get_tts_client())
        logger.debug("Registered TTSClient for capability=%s", TTS)
    except Exception as exc:
        logger.warning("Failed to register TTS capability: %s", exc)

    _register_stt_if_available(registry)


def _register_stt_if_available(registry: CapabilityRegistry) -> None:
    """Register one STT adapter per available language in the SpeechProvider registry (#11617).

    Imports lazily so voice-processing heavy deps are not pulled in at module
    load time.  Skips silently when no provider is configured.

    Enumerates ``ProviderRegistry._providers`` (language → priority-list) and
    registers a ``SpeechProviderSTTAdapter`` for each language's highest-priority
    provider, so every configured language is reachable via the STT capability.
    """
    try:
        from integrations.stt_adapter import SpeechProviderSTTAdapter
        from voice_processing.providers import get_speech_provider_registry
    except Exception as exc:
        logger.debug("voice_processing unavailable — STT capability not registered: %s", exc)
        return

    try:
        speech_registry = get_speech_provider_registry()
        languages = list(getattr(speech_registry, "_providers", {}).keys())
        if not languages:
            logger.debug("No STT providers registered in speech registry — STT capability skipped")
            return
        for lang in languages:
            _register_stt_language(registry, speech_registry, lang, SpeechProviderSTTAdapter)
    except Exception as exc:
        logger.warning("Failed to register STT capability: %s", exc)


def _register_stt_language(registry: CapabilityRegistry, speech_registry, lang: str, adapter_cls) -> None:
    """Register one STT adapter for *lang* if its highest-priority provider exists."""
    try:
        provider = speech_registry.get_provider(lang)
        if provider is None:
            logger.debug("No STT provider for language '%s' — skipped", lang)
            return
        registry.register(STT, adapter_cls(provider))
        logger.debug(
            "Registered SpeechProviderSTTAdapter (%s, lang=%s) for capability=%s",
            provider.provider_name,
            lang,
            STT,
        )
    except Exception as exc:
        logger.warning("Failed to register STT capability for language '%s': %s", lang, exc)


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
