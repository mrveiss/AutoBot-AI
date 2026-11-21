# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Generic Speech Provider

Wraps existing AutoBot speech recognition (Google/Sphinx/Whisper)
for languages without specialized providers.
Part of Issue MVA-2185.
"""

import io
import os
import time
import wave
from typing import List, Optional

from autobot_shared.audio_params import STT_CHANNELS, STT_SAMPLE_RATE, describe_wav
from autobot_shared.audio_wav import wav_duration_seconds
from autobot_shared.logging_manager import get_logger
from voice_processing.models import AudioInput, SpeechRecognitionResult
from voice_processing.providers import (
    ProviderFailed,
    ProviderUnavailable,
    SpeechProvider,
    TranscriptSegment,
    failures_as_provider_failed,
)
from voice_processing.speech_recognition import SpeechRecognitionEngine

logger = get_logger(__name__)

#: Languages the generic provider (and the local Whisper provider, #17778) cover.
GENERIC_LANGUAGES = (
    "en",  # English
    "de",  # German
    "es",  # Spanish
    "fr",  # French
    "ru",  # Russian
    "zh",  # Chinese
    "ja",  # Japanese
    "ko",  # Korean
)


class GenericProvider(SpeechProvider):
    """Generic speech provider using AutoBot's existing recognition engine."""

    is_external = True  # recognize_google sends the audio to a third party
    external_when_local_unavailable = True  # #17781 AC3: the owner-decided fallback for missing Whisper

    def __init__(self):
        """Initialize generic provider with speech recognition engine."""
        self.engine = SpeechRecognitionEngine()

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe audio using generic recognition engine.

        Args:
            audio_path: Path to audio file
            language: BCP-47 language code (e.g., 'en', 'de')

        Returns:
            List of transcript segments
        """
        if not self.is_available():
            raise ProviderUnavailable("Generic: the SpeechRecognition library is not available")
        if not os.path.exists(audio_path):
            raise ProviderFailed("Generic: audio file not found")
        with failures_as_provider_failed(self.provider_name):
            audio_input = await self._load_audio_input(audio_path)
            if "load_error" in audio_input.metadata:
                raise ProviderFailed(f"Generic: {audio_input.metadata['load_error']}")
            lang = language or "en"
            result: SpeechRecognitionResult = await self.engine.transcribe_audio(audio_input, language=lang)
            segments = self._convert_to_segments(result)
        logger.info("Generic provider transcription completed: %d segments", len(segments))
        return segments

    def is_available(self) -> bool:
        """Generic can run only when the engine has a recognizer (the SpeechRecognition library)."""
        return self.engine.recognizer is not None

    async def _load_audio_input(self, audio_path: str) -> AudioInput:
        """Load a WAV file into a complete AudioInput.

        Sample rate, channel count and sample width come from the WAV header
        (``describe_wav``), not from assumptions. Issue #17778: both constructions
        here omitted the required ``format``/``channels``/``timestamp`` fields, so
        every call raised ``TypeError`` and ``transcribe`` reported ``[]``.

        Args:
            audio_path: Path to audio file

        Returns:
            AudioInput; on an unreadable file one with empty data and ``load_error``.
        """
        try:
            return self._wav_audio_input(audio_path)
        except Exception as e:
            logger.error(f"Failed to load audio file {audio_path}: {e}")
            return AudioInput(
                audio_id=os.path.basename(audio_path),
                audio_data=b"",
                sample_rate=STT_SAMPLE_RATE,
                duration=0.0,
                format="wav",
                channels=STT_CHANNELS,
                timestamp=time.time(),
                metadata={"source_file": audio_path, "load_error": str(e)},
            )

    @staticmethod
    def _wav_audio_input(audio_path: str) -> AudioInput:
        """Read *audio_path* as WAV; raises on a corrupt or non-WAV file."""
        with open(audio_path, "rb") as fh:
            data = fh.read()
        fmt = describe_wav(data)
        if fmt.sample_rate <= 0:
            # A corrupt header is a load error, not a zero-duration input nobody
            # mentions (review on #17887): the shared duration helper never raises.
            raise ValueError(f"WAV header declares frame rate {fmt.sample_rate}")
        with wave.open(io.BytesIO(data), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            duration = wav_duration_seconds(wav)
        return AudioInput(
            audio_id=os.path.basename(audio_path),
            audio_data=frames,
            sample_rate=fmt.sample_rate,
            duration=duration,
            format=fmt.container,
            channels=fmt.channels,
            timestamp=time.time(),
            metadata={"source_file": audio_path, "sample_width": fmt.sample_width},
        )

    def _convert_to_segments(self, result: SpeechRecognitionResult) -> List[TranscriptSegment]:
        """Convert SpeechRecognitionResult to TranscriptSegments.

        Args:
            result: Speech recognition result

        Returns:
            List of transcript segments
        """
        segments = []
        if not result.transcription.strip():
            return segments  # the engine ran and heard nothing

        # If we have speech segments with timing, use those
        if result.speech_segments:
            for seg in result.speech_segments:
                segments.append(
                    TranscriptSegment(
                        text=result.transcription,
                        start_time=seg.get("start_time", 0.0),
                        end_time=seg.get("end_time", 0.0),
                        confidence=result.confidence,
                        language=result.language,
                    )
                )
        else:
            # No timing information - create single segment
            segments.append(
                TranscriptSegment(
                    text=result.transcription,
                    start_time=0.0,
                    end_time=0.0,  # Unknown duration
                    confidence=result.confidence,
                    language=result.language,
                )
            )

        return segments

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "Generic (Google/Sphinx)"

    @property
    def supported_languages(self) -> List[str]:
        """Return supported languages.

        Generic provider supports many languages via Google Speech API.
        """
        return list(GENERIC_LANGUAGES)
