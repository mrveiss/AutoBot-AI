# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AssemblyAI cloud ASR adapter (Issue #10147).

Env var: ASSEMBLYAI_API_KEY
API:     AssemblyAI v2 upload → submit (speaker_labels=true) → poll
Privacy: Audio is sent off-box — opt-in only (key must be set explicitly).
"""

import asyncio
import os
from typing import List, Optional

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import TranscriptSegment
from voice_processing.providers.cloud.base import CloudSpeechProvider

logger = get_logger(__name__)

_BASE_URL = "https://api.assemblyai.com/v2"
_POLL_INTERVAL = 3.0
_POLL_TIMEOUT = 600.0


class AssemblyAIProvider(CloudSpeechProvider):
    """AssemblyAI batch-transcription provider with speaker diarization."""

    _api_key_env = "ASSEMBLYAI_API_KEY"

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Upload, submit, poll AssemblyAI; return diarized segments."""
        if not self.is_configured:
            logger.error("AssemblyAIProvider: ASSEMBLYAI_API_KEY not set")
            return []
        if not os.path.exists(audio_path):
            logger.error("AssemblyAIProvider: audio file not found: %s", audio_path)
            return []
        try:
            with open(audio_path, "rb") as fh:
                audio_bytes = fh.read()
            upload_url = await self._upload(audio_bytes)
            transcript_id = await self._submit(upload_url, language)
            return await self._poll(transcript_id, language)
        except Exception as exc:
            logger.error("AssemblyAIProvider: transcription failed: %s", exc)
            return []

    def _headers(self) -> dict:
        return {"authorization": self._api_key or "", "content-type": "application/json"}

    async def _upload(self, audio_bytes: bytes) -> str:
        """Upload raw audio and return the AssemblyAI upload_url."""
        headers = {"authorization": self._api_key or "", "content-type": "application/octet-stream"}
        async with self._make_session() as session:
            async with session.post(f"{_BASE_URL}/upload", headers=headers, data=audio_bytes) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"AssemblyAI upload failed: {resp.status}")
                data = await resp.json()
        return data["upload_url"]

    async def _submit(self, upload_url: str, language: Optional[str]) -> str:
        """Submit transcription job with speaker_labels; return transcript id."""
        payload: dict = {"audio_url": upload_url, "speaker_labels": True}
        if language:
            payload["language_code"] = language
        async with self._make_session() as session:
            async with session.post(f"{_BASE_URL}/transcript", headers=self._headers(), json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"AssemblyAI submit failed: {resp.status}")
                data = await resp.json()
        return data["id"]

    async def _poll(self, transcript_id: str, language: Optional[str]) -> List[TranscriptSegment]:
        """Poll until complete or timeout; return parsed segments."""
        elapsed = 0.0
        async with self._make_session() as session:
            while elapsed < _POLL_TIMEOUT:
                async with session.get(f"{_BASE_URL}/transcript/{transcript_id}", headers=self._headers()) as resp:
                    data = await resp.json()
                status = data.get("status")
                if status == "completed":
                    return self._parse(data, language)
                if status == "error":
                    logger.error("AssemblyAIProvider: job error: %s", data.get("error"))
                    return []
                await asyncio.sleep(_POLL_INTERVAL)
                elapsed += _POLL_INTERVAL
        logger.error("AssemblyAIProvider: poll timeout after %.0fs", _POLL_TIMEOUT)
        return []

    def _parse(self, data: dict, language: Optional[str]) -> List[TranscriptSegment]:
        """Map AssemblyAI utterances to TranscriptSegments."""
        segments: List[TranscriptSegment] = []
        try:
            for utt in data.get("utterances") or []:
                speaker = f"SPEAKER_{utt.get('speaker', 'A')}"
                segments.append(
                    TranscriptSegment(
                        text=utt.get("text", ""),
                        start_time=utt.get("start", 0) / 1000.0,
                        end_time=utt.get("end", 0) / 1000.0,
                        confidence=float(utt.get("confidence", 0.0)),
                        language=language,
                        speaker=speaker,
                    )
                )
        except Exception as exc:
            logger.error("AssemblyAIProvider: parse error: %s", exc)
        return segments

    @property
    def provider_name(self) -> str:
        return "AssemblyAI"

    @property
    def supported_languages(self) -> List[str]:
        return ["en", "de", "es", "fr", "it", "pt", "nl", "hi", "ja", "zh", "fi", "ko", "pl", "ru", "tr", "uk"]
