# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Follow-up realtime provider seams (Issue #9025).

These declare the extension points for additional realtime voice providers
named in the AC (Gemini Live, ElevenLabs Conversational, Ultravox). They are
NOT fake implementations: each reports ``is_configured`` honestly from its
credential env var and raises ``RealtimeProviderError`` (503) from negotiate()
until the concrete upstream handshake is wired in a follow-up.

This keeps the registry/selection/UI surface complete (providers appear with
their capabilities + configured state) without shipping broken impls. Wiring a
provider = replace its ``negotiate()`` body with the real handshake; the rest
of the architecture is unchanged.
"""

from __future__ import annotations

import os

from autobot_shared.logging_manager import get_logger
from voice_processing.realtime.base import (
    RealtimeCapabilities,
    RealtimeNegotiation,
    RealtimeProviderError,
    RealtimeTransport,
    RealtimeVoiceProvider,
)

logger = get_logger(__name__)


class _SeamProvider(RealtimeVoiceProvider):
    """Base for not-yet-wired realtime providers.

    Subclasses set provider_id, a display name, a credential env var and a
    transport. negotiate() refuses cleanly until the upstream is implemented.
    """

    _display_name: str = ""
    _credential_env: str = ""
    _transport: RealtimeTransport = RealtimeTransport.WEBSOCKET
    _supports_cost_tracking: bool = False

    @property
    def provider_name(self) -> str:
        return self._display_name

    @property
    def is_configured(self) -> bool:
        return bool(self._credential_env and os.environ.get(self._credential_env))

    @property
    def capabilities(self) -> RealtimeCapabilities:
        return RealtimeCapabilities(
            transport=self._transport,
            supports_tools=True,
            supports_audio_output=True,
            supports_cost_tracking=self._supports_cost_tracking,
        )

    async def negotiate(
        self,
        *,
        offer: str,
        session_config: str,
        session_id: str,
    ) -> RealtimeNegotiation:
        logger.warning(
            "Realtime provider %r selected but its upstream handshake is not yet implemented (#9025 follow-up)",
            self.provider_id,
        )
        raise RealtimeProviderError(
            f"Realtime provider '{self.provider_id}' is not yet available — wire its upstream handshake (#9025).",
            status=503,
        )


class GeminiLiveProvider(_SeamProvider):
    """Gemini Live realtime provider seam (AC stretch goal)."""

    provider_id = "gemini"
    _display_name = "Gemini Live"
    _credential_env = "GEMINI_API_KEY"
    _transport = RealtimeTransport.WEBSOCKET
    _supports_cost_tracking = True


class ElevenLabsConversationalProvider(_SeamProvider):
    """ElevenLabs Conversational AI realtime provider seam."""

    provider_id = "elevenlabs"
    _display_name = "ElevenLabs Conversational"
    _credential_env = "ELEVENLABS_API_KEY"
    _transport = RealtimeTransport.WEBSOCKET


class UltravoxProvider(_SeamProvider):
    """Ultravox realtime provider seam."""

    provider_id = "ultravox"
    _display_name = "Ultravox"
    _credential_env = "ULTRAVOX_API_KEY"
    _transport = RealtimeTransport.WEBSOCKET
