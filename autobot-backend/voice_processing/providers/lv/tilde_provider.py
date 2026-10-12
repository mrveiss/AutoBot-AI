# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tilde Provider for Latvian Speech Recognition

Cloud-based Tilde ASR provider for Latvian language.
Part of Issue MVA-2185.
"""

import os
from typing import List, Optional

import aiohttp

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import (
    ProviderFailed,
    ProviderUnavailable,
    SpeechProvider,
    TranscriptSegment,
    failures_as_provider_failed,
)

logger = get_logger(__name__)


class TildeProvider(SpeechProvider):
    """Tilde cloud ASR provider for Latvian speech recognition."""

    is_external = True  # audio is posted to the Tilde service

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        """Initialize Tilde provider.

        Args:
            api_key: Tilde API key (defaults to env var)
            api_url: Tilde API URL (defaults to env var or public endpoint)
        """
        from services.provider_key_vault import VaultKeyUnavailableError, resolve_provider_key

        self._refusal = ""
        try:  # vault first; env as a logged fallback; an unreadable vault key is refused (#18094)
            self.api_key = api_key or resolve_provider_key("TILDE_API_KEY", os.getenv("TILDE_API_KEY", "")) or None
        except VaultKeyUnavailableError as exc:
            self.api_key, self._refusal = None, str(exc)
            logger.error("Tilde provider unavailable: %s", exc)
        self.api_url = api_url or os.getenv("TILDE_API_URL", "https://api.tilde.com/v1/asr")

        if not self.api_key:
            logger.debug(
                "TILDE_API_KEY not set - Tilde provider will not work. " "Set TILDE_API_KEY environment variable."
            )

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe audio using Tilde ASR.

        Args:
            audio_path: Path to audio file
            language: Language hint (ignored for Tilde - Latvian only)

        Returns:
            List of transcript segments
        """
        if self._refusal:
            raise ProviderUnavailable(f"Tilde: {self._refusal}")
        if not self.api_key:
            raise ProviderUnavailable("Tilde: TILDE_API_KEY not configured")
        if not os.path.exists(audio_path):
            raise ProviderFailed("Tilde: audio file not found")
        with failures_as_provider_failed(self.provider_name):
            with open(audio_path, "rb") as f:
                audio_data = f.read()
            segments = await self._call_tilde_api(audio_data, audio_path)
        logger.info("Tilde transcription completed: %d segments", len(segments))
        return segments

    def is_available(self) -> bool:
        """Tilde can run only with an API key."""
        return bool(self.api_key)

    async def _call_tilde_api(self, audio_data: bytes, audio_path: str) -> List[TranscriptSegment]:
        """Call Tilde ASR API.

        Args:
            audio_data: Audio file bytes
            audio_path: Original file path (for filename)

        Returns:
            List of transcript segments
        """
        # Prepare multipart form data
        form = aiohttp.FormData()
        form.add_field("audio", audio_data, filename=os.path.basename(audio_path), content_type="audio/wav")
        form.add_field("language", "lv")
        form.add_field("format", "json")
        form.add_field("segments", "true")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        timeout = aiohttp.ClientTimeout(total=300)  # 5 minute timeout

        from autobot_shared.http_client import get_http_client

        async with get_http_client().tracked_request(
            "POST", self.api_url, data=form, headers=headers, timeout=timeout
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error("Tilde API error %s: %s", response.status, error_text[:200])
                raise ProviderFailed(f"Tilde API error {response.status}")

            result = await response.json()
            return self._parse_tilde_response(result)

    def _parse_tilde_response(self, response: dict) -> List[TranscriptSegment]:
        """Parse Tilde API response into TranscriptSegments.

        Args:
            response: JSON response from Tilde API

        Returns:
            List of transcript segments
        """
        # Tilde format (assumed):
        # {
        #   "transcription": {
        #     "segments": [
        #       {
        #         "text": "...",
        #         "start": 0.0,
        #         "end": 1.5,
        #         "confidence": 0.95
        #       },
        #       ...
        #     ]
        #   }
        # }

        segments = []
        transcription = response.get("transcription", {})

        for seg in transcription.get("segments", []):
            segments.append(
                TranscriptSegment(
                    text=seg.get("text", ""),
                    start_time=seg.get("start", 0.0),
                    end_time=seg.get("end", 0.0),
                    confidence=seg.get("confidence", 0.0),
                    language="lv",
                )
            )

        return segments

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "Tilde"

    @property
    def supported_languages(self) -> List[str]:
        """Return supported languages."""
        return ["lv", "lat"]  # Latvian
