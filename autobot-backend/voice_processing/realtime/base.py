# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
RealtimeVoiceProvider abstract base + supporting types (Issue #9025).

Every realtime voice backend (OpenAI Realtime, Gemini Live, ElevenLabs
Conversational, Ultravox) implements ``RealtimeVoiceProvider``. The SDP-proxy
endpoint and the MCP tool bridge talk only to this interface, so providers are
drop-in.

Design mirrors ``voice_processing.providers.SpeechProvider``: an abstract base
with a ``provider_name`` / ``is_configured`` contract, credential-gated so a
provider is only offered when its API key is present.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RealtimeTransport(str, Enum):
    """Negotiation transport a realtime provider speaks.

    WEBRTC   — browser sends an SDP offer, provider returns an SDP answer
               (OpenAI Realtime today).
    WEBSOCKET — browser opens a websocket; provider returns connection params
               (Gemini Live / ElevenLabs Conversational pattern).
    """

    WEBRTC = "webrtc"
    WEBSOCKET = "websocket"


class RealtimeProviderError(Exception):
    """Raised when a provider cannot service a negotiation request.

    Carries an HTTP-ish ``status`` so the endpoint can map it consistently:
    503 = provider not configured/available, 502 = upstream error.
    """

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class RealtimeCapabilities:
    """Static declaration of what a realtime provider supports.

    Surfaced to the frontend so it can adapt the UI (e.g. choose WebRTC vs
    websocket transport, hide tool-calling toggles when unsupported).
    """

    transport: RealtimeTransport
    #: provider can register MCP/function tools mid-session
    supports_tools: bool = True
    #: provider streams model audio back (TTS) over the same channel
    supports_audio_output: bool = True
    #: provider emits per-turn token/audio usage for cost tracking
    supports_cost_tracking: bool = False


@dataclass
class RealtimeNegotiation:
    """Provider-neutral result of negotiating a realtime session.

    For WebRTC providers ``answer`` holds the SDP answer body and
    ``media_type`` is ``application/sdp``. For websocket providers ``answer``
    holds a JSON connection descriptor (URL + ephemeral token) and
    ``media_type`` is ``application/json``.
    """

    answer: bytes
    media_type: str = "application/sdp"
    #: extra response headers (provider may surface ephemeral session ids etc.)
    headers: dict[str, str] = field(default_factory=dict)


class RealtimeVoiceProvider(ABC):
    """Abstract base for a swappable realtime voice provider.

    Concrete providers wrap a single upstream realtime API. The negotiate()
    method is transport-agnostic: it consumes the browser's offer and returns
    a :class:`RealtimeNegotiation` the endpoint relays back verbatim.

    Tool registration is handled by the existing ``RealtimeMCPBridge`` which is
    already provider-neutral, so providers do not re-implement tool routing —
    they only declare ``supports_tools`` in their capabilities.
    """

    #: stable lowercase id used for config selection (e.g. "openai", "gemini")
    provider_id: str = ""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for logging/UI."""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True when this provider has the credentials it needs to run."""

    @property
    @abstractmethod
    def capabilities(self) -> RealtimeCapabilities:
        """Return this provider's static capability declaration."""

    @abstractmethod
    async def negotiate(
        self,
        *,
        offer: str,
        session_config: str,
        session_id: str,
    ) -> RealtimeNegotiation:
        """Negotiate a realtime session and return a provider-neutral answer.

        Args:
            offer: the browser's WebRTC SDP offer (or websocket handshake blob)
            session_config: provider session configuration JSON from the client
            session_id: AutoBot-generated id for telemetry correlation

        Returns:
            RealtimeNegotiation with the answer body the endpoint relays.

        Raises:
            RealtimeProviderError: when the provider is unconfigured (status
                503) or the upstream negotiation fails (status 502).
        """

    def describe(self) -> dict[str, Any]:
        """Return JSON-safe metadata (never credentials) for the providers API."""
        caps = self.capabilities
        return {
            "id": self.provider_id,
            "name": self.provider_name,
            "configured": self.is_configured,
            "transport": caps.transport.value,
            "supports_tools": caps.supports_tools,
            "supports_audio_output": caps.supports_audio_output,
            "supports_cost_tracking": caps.supports_cost_tracking,
        }
