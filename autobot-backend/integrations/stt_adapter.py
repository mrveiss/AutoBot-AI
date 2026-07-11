# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SpeechProvider → STTProtocol adapter (#11559).

Adapts ``voice_processing.providers.SpeechProvider`` (ABC with language-keyed
registry) to the ``integrations.protocols.STTProtocol`` surface so capability
consumers can resolve STT without knowing the concrete provider.

Transcription results are normalised from ``TranscriptSegment`` dataclasses to
plain dicts (keys: ``text``, ``start_time``, ``end_time``, ``confidence``).

Import is lazy so heavy voice-processing deps are only pulled in if a provider
is actually registered.  Missing deps are logged and registration is skipped
(mirrors the TTS registration pattern in ``capability_registry.py``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voice_processing.providers import SpeechProvider

logger = logging.getLogger(__name__)


class SpeechProviderSTTAdapter:
    """Adapts a ``SpeechProvider`` instance to satisfy ``STTProtocol``.

    Maps:
    - ``transcribe(audio_path, language)`` → ``provider.transcribe(...)``
      Returns ``list[dict]`` with keys: ``text``, ``start_time``,
      ``end_time``, ``confidence``.
    """

    def __init__(self, provider: SpeechProvider) -> None:
        self._provider = provider

    async def transcribe(self, audio_path: str, language: str | None = None) -> list[dict]:
        """Transcribe audio at *audio_path* via the wrapped SpeechProvider.

        Args:
            audio_path: Filesystem path to the audio file.
            language:   Optional BCP-47 language hint passed to the provider.

        Returns:
            List of transcript-segment dicts (``text``, ``start_time``,
            ``end_time``, ``confidence``).  Returns ``[]`` on provider error.
        """
        try:
            segments = await self._provider.transcribe(audio_path, language=language)
        except Exception as exc:
            logger.warning("SpeechProviderSTTAdapter.transcribe failed: %s", exc)
            return []
        return [_segment_to_dict(seg) for seg in segments]


def _segment_to_dict(segment) -> dict:
    """Convert a ``TranscriptSegment`` dataclass to a plain dict."""
    return {
        "text": segment.text,
        "start_time": float(segment.start_time),
        "end_time": float(segment.end_time),
        "confidence": float(segment.confidence),
    }
