# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Deepgram cloud ASR adapter (Issue #10147).

Env var: DEEPGRAM_API_KEY
API:     Deepgram Listen REST API with diarize=true
Privacy: Audio is sent off-box — opt-in only (key must be set explicitly).
"""

import os
from typing import List, Optional

import aiohttp

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import TranscriptSegment
from voice_processing.providers.cloud.base import CloudSpeechProvider

logger = get_logger(__name__)

_DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


class DeepgramProvider(CloudSpeechProvider):
    """Deepgram batch-transcription provider with built-in speaker diarization."""

    _api_key_env = "DEEPGRAM_API_KEY"

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe audio via Deepgram Listen API."""
        if not self.is_configured:
            logger.error("DeepgramProvider: DEEPGRAM_API_KEY not set")
            return []
        if not os.path.exists(audio_path):
            logger.error("DeepgramProvider: audio file not found: %s", audio_path)
            return []
        try:
            with open(audio_path, "rb") as fh:
                audio_bytes = fh.read()
            return await self._call_api(audio_bytes, language)
        except Exception as exc:
            logger.error("DeepgramProvider: transcription failed: %s", exc)
            return []

    async def _call_api(self, audio_bytes: bytes, language: Optional[str]) -> List[TranscriptSegment]:
        """POST audio to Deepgram and parse the response."""
        params = {"diarize": "true", "punctuate": "true", "utterances": "false"}
        if language:
            params["language"] = language
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "audio/wav",
        }
        async with self._make_session() as session:
            async with session.post(_DEEPGRAM_URL, params=params, headers=headers, data=audio_bytes) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    logger.error("DeepgramProvider: API error %d: %s", resp.status, err[:200])
                    return []
                data = await resp.json()
        return self._parse(data, language)

    def _parse(self, data: dict, language: Optional[str]) -> List[TranscriptSegment]:
        """Map Deepgram Listen JSON to TranscriptSegments."""
        segments: List[TranscriptSegment] = []
        try:
            channels = data.get("results", {}).get("channels", [])
            words = channels[0].get("alternatives", [{}])[0].get("words", []) if channels else []
            for w in words:
                speaker = f"SPEAKER_{int(w.get('speaker', 0)):02d}"
                segments.append(
                    TranscriptSegment(
                        text=w.get("word", ""),
                        start_time=float(w.get("start", 0.0)),
                        end_time=float(w.get("end", 0.0)),
                        confidence=float(w.get("confidence", 0.0)),
                        language=language,
                        speaker=speaker,
                    )
                )
        except Exception as exc:
            logger.error("DeepgramProvider: parse error: %s", exc)
        return segments

    @property
    def provider_name(self) -> str:
        return "Deepgram"

    @property
    def supported_languages(self) -> List[str]:
        return ["en", "de", "es", "fr", "it", "pt", "nl", "hi", "ja", "zh", "ru", "sv", "da", "fi", "ko"]
