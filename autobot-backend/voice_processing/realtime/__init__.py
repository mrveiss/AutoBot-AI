# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Multi-provider realtime voice architecture (Issue #9025).

Defines a provider-agnostic realtime voice layer so the backend can swap the
realtime STT/TTS provider (OpenAI Realtime, Gemini Live, ElevenLabs
Conversational, Ultravox) without re-engineering the SDP-proxy endpoint or the
MCP tool bridge.

Mirrors the established ASR provider pattern in ``voice_processing.providers``
(protocol + registry + config-driven selection, credential-gated).

Public surface:
    RealtimeVoiceProvider   — abstract base every realtime provider implements
    RealtimeCapabilities    — declares transport + feature support per provider
    RealtimeNegotiation     — provider-neutral SDP/offer negotiation result
    RealtimeTransport       — supported negotiation transports
    RealtimeProviderError   — raised when a provider cannot service a request
"""

from voice_processing.realtime.base import (
    RealtimeCapabilities,
    RealtimeNegotiation,
    RealtimeProviderError,
    RealtimeTransport,
    RealtimeVoiceProvider,
)

__all__ = [
    "RealtimeVoiceProvider",
    "RealtimeCapabilities",
    "RealtimeNegotiation",
    "RealtimeTransport",
    "RealtimeProviderError",
]
