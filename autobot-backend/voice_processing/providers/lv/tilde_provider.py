# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tilde Provider for Latvian Speech Recognition

Cloud-based Tilde ASR provider for Latvian language.
Part of Issue MVA-2185.
"""

import asyncio
import os
from typing import List, Optional

import aiohttp

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import SpeechProvider, TranscriptSegment

logger = get_logger(__name__)


class TildeProvider(SpeechProvider):
    """Tilde cloud ASR provider for Latvian speech recognition."""

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
        self.api_key = api_key or os.getenv("TILDE_API_KEY")
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
        if not self.api_key:
            logger.error("Tilde API key not configured")
            return []

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return []

        try:
            # Read audio file
            with open(audio_path, "rb") as f:
                audio_data = f.read()

            # Send to Tilde API
            segments = await self._call_tilde_api(audio_data, audio_path)
            logger.info(f"Tilde transcription completed: {len(segments)} segments")
            return segments

        except Exception as e:
            logger.error(f"Tilde transcription failed: {e}")
            return []

    async def _call_tilde_api(self, audio_data: bytes, audio_path: str) -> List[TranscriptSegment]:
        """Call Tilde ASR API.

        Args:
            audio_data: Audio file bytes
            audio_path: Original file path (for filename)

        Returns:
            List of transcript segments
        """
        try:
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

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.api_url,
                    data=form,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Tilde API error {response.status}: {error_text}")
                        return []

                    result = await response.json()
                    return self._parse_tilde_response(result)

        except asyncio.TimeoutError:
            logger.error("Tilde API request timed out after 5 minutes")
            return []
        except Exception as e:
            logger.error(f"Tilde API call failed: {e}")
            return []

    def _parse_tilde_response(self, response: dict) -> List[TranscriptSegment]:
        """Parse Tilde API response into TranscriptSegments.

        Args:
            response: JSON response from Tilde API

        Returns:
            List of transcript segments
        """
        try:
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

        except Exception as e:
            logger.error(f"Failed to parse Tilde response: {e}")
            return []

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "Tilde"

    @property
    def supported_languages(self) -> List[str]:
        """Return supported languages."""
        return ["lv", "lat"]  # Latvian
