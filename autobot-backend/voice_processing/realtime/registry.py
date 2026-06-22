# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Realtime voice provider registry + config-driven selection (Issue #9025).

Mirrors ``voice_processing.providers.selection`` for the ASR tier:

- A provider map keyed by stable id.
- The active provider id comes from an in-process override (set per request)
  falling back to ``AUTOBOT_VOICE_REALTIME_PROVIDER`` (ssot_config), defaulting
  to "openai" — so the default realtime behaviour is unchanged (back-compat).
- ``get_active_realtime_provider`` resolves the selected provider; if the
  selection is unknown or the selected provider is unconfigured it falls back
  to the default OpenAI provider (which itself reports unconfigured cleanly when
  no key is present), so a bad config never crashes the endpoint.
"""

from __future__ import annotations

from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config
from voice_processing.realtime.base import RealtimeVoiceProvider
from voice_processing.realtime.openai_provider import OpenAIRealtimeProvider
from voice_processing.realtime.seam import (
    ElevenLabsConversationalProvider,
    GeminiLiveProvider,
    UltravoxProvider,
)

logger = get_logger(__name__)

_DEFAULT_PROVIDER_ID = "openai"

# Ordered so the default (openai) is first in any listing.
_PROVIDER_MAP: dict[str, type[RealtimeVoiceProvider]] = {
    "openai": OpenAIRealtimeProvider,
    "gemini": GeminiLiveProvider,
    "elevenlabs": ElevenLabsConversationalProvider,
    "ultravox": UltravoxProvider,
}

# In-process per-conversation override (lost on restart; env is source of truth).
_active_override: Optional[str] = None


def _config_selected() -> str:
    """Return the configured realtime provider id, lower-cased."""
    cfg = get_config()
    raw = (getattr(cfg.misc, "voice_realtime_provider", "") or "").strip().lower()
    return raw or _DEFAULT_PROVIDER_ID


def get_active_provider_id() -> str:
    """Return the active provider id (override > config > default)."""
    return (_active_override or _config_selected() or _DEFAULT_PROVIDER_ID).lower()


def set_active_provider(provider_id: Optional[str]) -> None:
    """Set the in-process active realtime provider override.

    Pass ``None`` to clear the override and fall back to config/default.
    Process-local — configure AUTOBOT_VOICE_REALTIME_PROVIDER for persistence.
    """
    global _active_override
    if provider_id is not None:
        normalized = provider_id.strip().lower()
        if normalized not in _PROVIDER_MAP:
            raise ValueError(f"Unknown realtime provider: {provider_id!r}. Valid: {list(_PROVIDER_MAP)}")
        _active_override = normalized
    else:
        _active_override = None
    logger.info("Active realtime voice provider set to: %s", _active_override or "(config default)")


def get_provider_by_id(provider_id: str) -> Optional[RealtimeVoiceProvider]:
    """Instantiate a provider by id, or None when the id is unknown."""
    cls = _PROVIDER_MAP.get(provider_id.lower())
    return cls() if cls else None


def get_active_realtime_provider() -> RealtimeVoiceProvider:
    """Resolve the active, configured realtime provider.

    Resolution order:
      1. The selected provider (override > config) when it is configured.
      2. Otherwise the default OpenAI provider.

    Always returns a provider instance (never None); the endpoint maps an
    unconfigured provider to a 503 via RealtimeProviderError at negotiate time.
    """
    selected_id = get_active_provider_id()
    provider = get_provider_by_id(selected_id)

    if provider is None:
        logger.warning(
            "Realtime provider %r is unknown — falling back to default %r", selected_id, _DEFAULT_PROVIDER_ID
        )
        return OpenAIRealtimeProvider()

    if not provider.is_configured and selected_id != _DEFAULT_PROVIDER_ID:
        logger.warning(
            "Selected realtime provider %r is not configured — falling back to default %r",
            selected_id,
            _DEFAULT_PROVIDER_ID,
        )
        return OpenAIRealtimeProvider()

    return provider


def list_realtime_providers() -> list[dict]:
    """Return JSON-safe metadata for every realtime provider (never credentials)."""
    return [cls().describe() for cls in _PROVIDER_MAP.values()]
