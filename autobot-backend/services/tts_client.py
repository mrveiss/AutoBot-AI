# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
TTS Worker Client Service (#1054)

Provides an async client for the Pocket TTS worker.
Returns raw WAV bytes for the caller to stream or play.

Usage:
    from services.tts_client import get_tts_client

    client = get_tts_client()
    if await client.is_available():
        wav_bytes = await client.synthesize("Hello world", voice_id="alba")
"""

import logging
import os

import aiohttp

from autobot_shared.ssot_config import get_config

logger = logging.getLogger(__name__)

_ssot = get_config()
TTS_WORKER_HOST = os.getenv("AUTOBOT_TTS_WORKER_HOST", _ssot.vm.tts)
TTS_WORKER_PORT = os.getenv("AUTOBOT_TTS_WORKER_PORT", str(_ssot.port.tts))
TTS_WORKER_URL = f"http://{TTS_WORKER_HOST}:{TTS_WORKER_PORT}"

HEALTH_TIMEOUT = 2.0
SYNTHESIS_TIMEOUT = 60.0

_client_instance: "TTSClient | None" = None


class TTSClient:
    """Async HTTP client for the AutoBot TTS worker."""

    def __init__(self, base_url: str = TTS_WORKER_URL) -> None:
        self.base_url = base_url

    async def is_available(self) -> bool:
        """Return True if the TTS worker health check passes."""
        try:
            timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("model_loaded", False)
        except Exception as e:
            logger.debug("TTS worker health check failed: %s", e)
        return False

    async def synthesize(self, text: str, voice_id: str = "") -> bytes:
        """Send text to TTS worker and return WAV bytes."""
        timeout = aiohttp.ClientTimeout(total=SYNTHESIS_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field("text", text)
            if voice_id:
                data.add_field("voice_id", voice_id)
            async with session.post(
                f"{self.base_url}/tts/synthesize", data=data
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"TTS worker error {resp.status}: {body}")
                return await resp.read()

    async def clone_voice(self, text: str, reference_audio: bytes) -> bytes:
        """Send text + reference audio to TTS worker; returns WAV bytes."""
        timeout = aiohttp.ClientTimeout(total=SYNTHESIS_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field("text", text)
            data.add_field(
                "reference_audio",
                reference_audio,
                filename="reference.wav",
                content_type="audio/wav",
            )
            async with session.post(
                f"{self.base_url}/tts/clone-voice", data=data
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"TTS worker error {resp.status}: {body}")
                return await resp.read()

    async def list_voices(self) -> list[dict]:
        """List available voice profiles from TTS worker."""
        timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/voices") as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.warning("Failed to list voices: %s", e)
        return []

    async def create_voice(
        self, name: str, audio_bytes: bytes, filename: str = "ref.wav"
    ) -> dict:
        """Create a voice profile from reference audio."""
        timeout = aiohttp.ClientTimeout(total=SYNTHESIS_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field("name", name)
            data.add_field(
                "audio",
                audio_bytes,
                filename=filename,
                content_type="audio/wav",
            )
            async with session.post(
                f"{self.base_url}/voices/create", data=data
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Voice create error {resp.status}: {body}")
                return await resp.json()

    async def delete_voice(self, voice_id: str) -> bool:
        """Delete a voice profile."""
        timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.delete(f"{self.base_url}/voices/{voice_id}") as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning("Failed to delete voice %s: %s", voice_id, e)
        return False


def get_tts_client() -> TTSClient:
    """Return the singleton TTSClient instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = TTSClient()
    return _client_instance
