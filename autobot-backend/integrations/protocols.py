# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Vendor-neutral capability Protocols for messaging and voice integrations (#11524).

Defines structural Protocols (PEP 544) for communication and voice capabilities.
Consumers resolve capabilities from ``integrations.capability_registry`` rather than
branching on provider names.

Design:
- ``MessagingProtocol``  — two-way text channel (send + fetch)
- ``TTSProtocol``        — text-to-speech synthesis
- ``STTProtocol``        — audio transcription
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MessagingProtocol(Protocol):
    """Structural protocol for two-way messaging integrations.

    Derived from the common surface of SlackIntegration and DiscordIntegration
    (the two integrations with the most complete send/receive support).

    All methods are async; implementations MUST NOT block the event loop.
    """

    async def send_message(self, channel_id: str, text: str, **kwargs) -> dict:
        """Send *text* to *channel_id*.

        Args:
            channel_id: Provider-specific channel/chat identifier.
            text:       Plain-text body of the message.
            **kwargs:   Optional provider extensions (e.g. ``blocks``, ``parse_mode``).

        Returns:
            Provider API response as a plain ``dict``.
        """
        ...

    async def fetch_messages(self, channel_id: str, limit: int = 100) -> list[dict]:
        """Fetch recent messages from *channel_id*.

        Args:
            channel_id: Provider-specific channel/chat identifier.
            limit:      Maximum number of messages to return.

        Returns:
            List of message dicts in reverse-chronological order.
        """
        ...


@runtime_checkable
class TTSProtocol(Protocol):
    """Structural protocol for text-to-speech synthesis.

    Derived from ``services.tts_client.TTSClient``'s public async surface.
    """

    async def synthesize(self, text: str, voice_id: str = "", language: str = "") -> bytes:
        """Synthesise *text* and return raw audio bytes (WAV).

        Args:
            text:     Utterance to synthesise.
            voice_id: Optional voice-profile identifier.
            language: Optional BCP-47 language hint.

        Returns:
            Raw WAV bytes.
        """
        ...

    async def is_available(self) -> bool:
        """Return ``True`` when the TTS back-end is reachable and ready."""
        ...


@runtime_checkable
class STTProtocol(Protocol):
    """Structural protocol for speech-to-text transcription.

    Derived from ``voice_processing.providers.SpeechProvider``'s async surface.
    """

    async def transcribe(self, audio_path: str, language: str | None = None) -> list[dict]:
        """Transcribe audio at *audio_path* to a list of segment dicts.

        Each dict MUST contain at minimum:
            ``{"text": str, "start_time": float, "end_time": float, "confidence": float}``

        Args:
            audio_path: Filesystem path to the audio file.
            language:   Optional BCP-47 language hint.

        Returns:
            List of transcript-segment dicts.
        """
        ...
