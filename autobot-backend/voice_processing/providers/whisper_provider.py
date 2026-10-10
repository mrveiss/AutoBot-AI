# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Local Whisper Speech Provider

The default transcriber when no cloud speech key is configured: the ONE pinned,
integrity-verified Whisper pipeline (``media.audio.pipeline``) behind the
``SpeechProvider`` interface. Issue #17778.
"""

import asyncio
from typing import List, Optional

from autobot_shared.logging_manager import get_logger
from media.audio.pipeline import get_whisper_pipeline, transcribe_path
from voice_processing.hallucination_filter import is_silence_hallucination
from voice_processing.providers import SpeechProvider, TranscriptSegment
from voice_processing.providers.generic_provider import GENERIC_LANGUAGES

logger = get_logger(__name__)

#: Same convention as ``POST /voice/transcribe`` (0.9 when there is text): the
#: HF pipeline reports no confidence, so one engine reports one number everywhere.
WHISPER_TEXT_CONFIDENCE = 0.9


class WhisperProvider(SpeechProvider):
    """Speech provider backed by the local pinned Whisper pipeline."""

    def is_available(self) -> bool:
        """True when the pinned pipeline can be (or already is) loaded."""
        return get_whisper_pipeline() is not None

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe *audio_path*; an empty list lets the registry fall through."""
        pipe = get_whisper_pipeline()
        if pipe is None:
            logger.warning("Whisper pipeline unavailable; provider yields no segments")
            return []
        result = await asyncio.to_thread(transcribe_path, pipe, audio_path, language=language or "")
        if not result.text or is_silence_hallucination(result.text, language or None):
            return []
        return [
            TranscriptSegment(
                text=result.text,
                start_time=0.0,
                end_time=0.0,  # return_timestamps=False: duration unknown
                confidence=WHISPER_TEXT_CONFIDENCE,
                language=language or result.language,
            )
        ]

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "Whisper (local, pinned)"

    @property
    def supported_languages(self) -> List[str]:
        """Languages Whisper is registered for: the ones the generic provider covers."""
        return list(GENERIC_LANGUAGES)
