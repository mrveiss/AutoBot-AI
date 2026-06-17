# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Google Cloud STT v2 adapter (Issue #10147).

Env var: GOOGLE_APPLICATION_CREDENTIALS (path to service-account JSON)
API:     google-cloud-speech v2 (SpeechClient) with DiarizationConfig
Privacy: Audio is sent to Google's Cloud — opt-in only.

Import guard: if google-cloud-speech is absent, is_configured returns False
and the class is never registered.  Pattern mirrors diarization_service.py.
"""

import os
from typing import List, Optional

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import TranscriptSegment
from voice_processing.providers.cloud.base import CloudSpeechProvider

logger = get_logger(__name__)

# Guarded import — google-cloud-speech is optional
_google_available = False
try:
    from google.cloud import speech as _google_speech  # type: ignore[import]

    _google_available = True
except ImportError:
    _google_speech = None  # module attribute always defined so callers/patchers can reference it
    logger.warning("google-cloud-speech not installed — GoogleSpeechProvider will not be available.")


class GoogleSpeechProvider(CloudSpeechProvider):
    """Google Cloud Speech-to-Text v2 with speaker diarization."""

    # Google uses a credentials file, not a simple API key.
    # We treat the credentials path as the "key" for is_configured.
    _api_key_env = "GOOGLE_APPLICATION_CREDENTIALS"

    def __init__(self) -> None:
        # Call super to log warning if env var unset
        super().__init__()
        # Override: the value is a file path, not a bearer token
        self._credentials_path: Optional[str] = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    @property
    def is_configured(self) -> bool:
        """True only when the google lib is present AND credentials file exists."""
        if not _google_available:
            return False
        return bool(self._credentials_path and os.path.isfile(self._credentials_path))

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe audio via Google Cloud STT v2 in a thread pool."""
        if not self.is_configured:
            logger.error("GoogleSpeechProvider: not configured (lib absent or credentials missing)")
            return []
        if not os.path.exists(audio_path):
            logger.error("GoogleSpeechProvider: audio file not found: %s", audio_path)
            return []
        try:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self._sync_transcribe, audio_path, language)
        except Exception as exc:
            logger.error("GoogleSpeechProvider: transcription failed: %s", exc)
            return []

    def _sync_transcribe(self, audio_path: str, language: Optional[str]) -> List[TranscriptSegment]:
        """Blocking Google STT call (run in thread pool)."""
        lang = language or "en-US"
        with open(audio_path, "rb") as fh:
            audio_bytes = fh.read()

        client = _google_speech.SpeechClient()  # type: ignore[union-attr]
        audio = _google_speech.RecognitionAudio(content=audio_bytes)  # type: ignore[union-attr]
        diarization_config = _google_speech.SpeakerDiarizationConfig(  # type: ignore[union-attr]
            enable_speaker_diarization=True,
            min_speaker_count=1,
            max_speaker_count=6,
        )
        config = _google_speech.RecognitionConfig(  # type: ignore[union-attr]
            encoding=_google_speech.RecognitionConfig.AudioEncoding.LINEAR16,  # type: ignore[union-attr]
            language_code=lang,
            diarization_config=diarization_config,
            enable_word_time_offsets=True,
        )
        response = client.recognize(config=config, audio=audio)
        return self._parse(response, language)

    def _parse(self, response: object, language: Optional[str]) -> List[TranscriptSegment]:
        """Map Google STT response words to TranscriptSegments."""
        segments: List[TranscriptSegment] = []
        try:
            results = getattr(response, "results", [])
            if not results:
                return segments
            # The last result contains full diarization info
            words = results[-1].alternatives[0].words
            for w in words:
                speaker = f"SPEAKER_{int(getattr(w, 'speaker_tag', 0)):02d}"
                start = w.start_time.total_seconds() if hasattr(w.start_time, "total_seconds") else 0.0
                end = w.end_time.total_seconds() if hasattr(w.end_time, "total_seconds") else 0.0
                segments.append(
                    TranscriptSegment(
                        text=w.word,
                        start_time=float(start),
                        end_time=float(end),
                        confidence=float(getattr(w, "confidence", 0.0)),
                        language=language,
                        speaker=speaker,
                    )
                )
        except Exception as exc:
            logger.error("GoogleSpeechProvider: parse error: %s", exc)
        return segments

    @property
    def provider_name(self) -> str:
        return "Google Cloud STT"

    @property
    def supported_languages(self) -> List[str]:
        return [
            "en",
            "en-US",
            "en-GB",
            "de",
            "es",
            "fr",
            "it",
            "pt",
            "nl",
            "hi",
            "ja",
            "zh",
            "ko",
            "ru",
            "lv",
            "pl",
            "sv",
            "da",
            "fi",
            "tr",
        ]
