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

from autobot_shared.audio_params import STT_SAMPLE_RATE
from autobot_shared.logging_manager import get_logger
from media.audio.decode import decode_audio_bytes
from media.audio.pipeline import WhisperTranscription, get_whisper_pipeline, transcribe_path, whisper_loadable
from voice_processing.hallucination_filter import is_silence_hallucination, peak_window_rms
from voice_processing.providers import SpeechProvider, TranscriptSegment
from voice_processing.providers.generic_provider import GENERIC_LANGUAGES

logger = get_logger(__name__)

#: Same convention as ``POST /voice/transcribe`` (0.9 when there is text): the
#: HF pipeline reports no confidence, so one engine reports one number everywhere.
WHISPER_TEXT_CONFIDENCE = 0.9


class WhisperUnavailableError(RuntimeError):
    """The pinned Whisper pipeline could not be loaded (a failure, not "no speech")."""


def _chunk_times(chunk: dict) -> tuple[float, float]:
    """(start, end) of a pipeline chunk; the last chunk's end may be None -> its start."""
    start, end = chunk.get("timestamp") or (0.0, None)
    start = float(start or 0.0)
    return start, float(end) if end is not None else start


def _segments_from(result: WhisperTranscription, language: str) -> List[TranscriptSegment]:
    """One TranscriptSegment per timestamped chunk; a single untimed one if there are none."""
    lang = language or result.language
    segments = []
    for chunk in result.chunks:
        text = (chunk.get("text") or "").strip()
        if text:
            start, end = _chunk_times(chunk)
            segments.append(TranscriptSegment(text, start, end, WHISPER_TEXT_CONFIDENCE, language=lang))
    if not segments:
        segments.append(TranscriptSegment(result.text, 0.0, 0.0, WHISPER_TEXT_CONFIDENCE, language=lang))
    return segments


class WhisperProvider(SpeechProvider):
    """Speech provider backed by the local pinned Whisper pipeline."""

    is_default_local = True

    def is_available(self) -> bool:
        """Cheap probe (never loads the model, safe on the event loop)."""
        return whisper_loadable()

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe *audio_path* with real chunk timestamps; [] means the audio had no speech.

        Raises :class:`WhisperUnavailableError` when the model could not be loaded, so the
        registry records a failure instead of a genuine empty transcript.

        The model load and the inference both run in a worker thread, so a caller's
        ``asyncio.wait_for`` can time out instead of being stuck behind them.
        """
        return await asyncio.to_thread(self._transcribe_blocking, audio_path, language or "")

    def _transcribe_blocking(self, audio_path: str, language: str) -> List[TranscriptSegment]:
        """Load (first use) and run Whisper with ``return_timestamps=True`` (any length)."""
        pipe = get_whisper_pipeline()
        if pipe is None:
            raise WhisperUnavailableError("Whisper pipeline could not be loaded")
        result = transcribe_path(pipe, audio_path, language=language, timestamps=True)
        if not result.text or self._is_phantom(result.text, audio_path, language):
            return []
        return _segments_from(result, language)

    @staticmethod
    def _is_phantom(text: str, audio_path: str, language: str) -> bool:
        """Silence-hallucination gate, with the peak RMS of the audio like VoiceProcessor (#13104)."""
        with open(audio_path, "rb") as fh:
            samples = decode_audio_bytes(fh.read())
        rms = peak_window_rms(samples, STT_SAMPLE_RATE)
        return is_silence_hallucination(text, language or None, rms=rms)

    @property
    def provider_name(self) -> str:
        """Display name: local Whisper with its weights pinned to a revision."""
        return "Whisper (local, pinned)"

    @property
    def supported_languages(self) -> List[str]:
        """Languages Whisper is registered for: the ones the generic provider covers."""
        return list(GENERIC_LANGUAGES)
