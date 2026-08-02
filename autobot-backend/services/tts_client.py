# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import aclosing

import aiohttp

from autobot_shared.env_utils import blank_to_none
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import TTL_5_MINUTES
from autobot_shared.ssot_config import config, get_config

logger = get_logger(__name__)

_ssot = get_config()
TTS_WORKER_HOST = config.tts_worker_host
TTS_WORKER_PORT = config.tts_worker_port
TTS_WORKER_URL = f"http://{TTS_WORKER_HOST}:{TTS_WORKER_PORT}"

HEALTH_TIMEOUT = 2.0
SYNTHESIS_TIMEOUT = 60.0

# #12886: a worker deployed before /tts/synthesize/stream existed 404s that
# route while serving /tts/synthesize normally. The backend caches that
# negative result for this long so it costs one failed round trip per window
# instead of one per utterance, and re-probes afterwards so a worker updated
# in place resumes streaming without a backend restart.
_STREAM_PROBE_TTL_DEFAULT = TTL_5_MINUTES


def _resolve_stream_probe_ttl() -> int:
    """Return seconds to cache a negative /tts/synthesize/stream probe."""
    raw = blank_to_none(config.misc.tts_stream_probe_ttl)
    if raw is None:
        return _STREAM_PROBE_TTL_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_TTS_STREAM_PROBE_TTL=%r is not an integer; falling back to %ds",
            raw,
            _STREAM_PROBE_TTL_DEFAULT,
        )
        return _STREAM_PROBE_TTL_DEFAULT
    if value <= 0:
        logger.warning(
            "AUTOBOT_TTS_STREAM_PROBE_TTL=%d must be positive; falling back to %ds",
            value,
            _STREAM_PROBE_TTL_DEFAULT,
        )
        return _STREAM_PROBE_TTL_DEFAULT
    return value


STREAM_PROBE_TTL = _resolve_stream_probe_ttl()

_client_instance: "TTSClient | None" = None


class TTSStreamUnsupported(RuntimeError):
    """The worker does not serve ``/tts/synthesize/stream`` (#12886).

    Distinct from a generic worker failure: it means the deployed worker's
    route table predates the backend calling it, so the whole-utterance route
    is the correct thing to use instead. Any other status is a real error and
    must not be retried against a different endpoint.
    """


class TTSClient:
    """Async HTTP client for the AutoBot TTS worker."""

    def __init__(self, base_url: str = TTS_WORKER_URL) -> None:
        self.base_url = base_url
        # monotonic deadline until which the streaming route is known-absent
        self._stream_absent_until: float = 0.0

    async def is_available(self) -> bool:
        """Return True if the TTS worker health check passes."""
        try:
            timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT)
            client = get_http_client()
            async with client.tracked_request(
                "GET", f"{self.base_url}/health", timeout=timeout, suppress_error_log=True
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("model_loaded", False)
        except Exception as e:
            logger.debug("TTS worker health check failed: %s", e)
        return False

    async def synthesize(self, text: str, voice_id: str = "", language: str = "") -> bytes:
        """Send text to TTS worker and return WAV bytes."""
        timeout = aiohttp.ClientTimeout(total=SYNTHESIS_TIMEOUT)
        data = aiohttp.FormData()
        data.add_field("text", text)
        if voice_id:
            data.add_field("voice_id", voice_id)
        if language:
            data.add_field("language", language)
        client = get_http_client()
        async with client.tracked_request(
            "POST", f"{self.base_url}/tts/synthesize", data=data, timeout=timeout
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"TTS worker error {resp.status}: {body}")
            return await resp.read()

    async def synthesize_stream(self, text: str, voice_id: str = "", language: str = "") -> AsyncIterator[bytes]:
        """Stream TTS audio from the worker as individually-decodable WAV chunks (#12501).

        Consumes the worker's length-prefixed framing
        (``[4-byte big-endian length][WAV bytes]``, see
        ``/tts/synthesize/stream`` in tts-worker.py.j2) and yields each
        chunk's raw WAV bytes as soon as it arrives, so the caller can
        forward audio to the client the instant the first ~250ms is ready
        instead of waiting for the whole utterance.
        """
        timeout = aiohttp.ClientTimeout(total=SYNTHESIS_TIMEOUT)
        data = aiohttp.FormData()
        data.add_field("text", text)
        if voice_id:
            data.add_field("voice_id", voice_id)
        if language:
            data.add_field("language", language)
        client = get_http_client()
        async with client.tracked_request(
            "POST", f"{self.base_url}/tts/synthesize/stream", data=data, timeout=timeout
        ) as resp:
            if resp.status in (404, 405):
                # Route table skew, not a synthesis failure — see #12886.
                raise TTSStreamUnsupported(f"TTS worker error {resp.status}: worker does not serve the stream route")
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"TTS worker error {resp.status}: {body}")
            while True:
                try:
                    header = await resp.content.readexactly(4)
                except asyncio.IncompleteReadError:
                    break
                chunk_len = int.from_bytes(header, "big")
                try:
                    yield await resp.content.readexactly(chunk_len)
                except asyncio.IncompleteReadError as e:
                    raise RuntimeError("TTS stream truncated mid-chunk") from e

    def _streaming_known_absent(self) -> bool:
        """True while a recent probe showed the worker lacks the stream route."""
        return time.monotonic() < self._stream_absent_until

    async def stream_or_synthesize(self, text: str, voice_id: str = "", language: str = "") -> AsyncIterator[bytes]:
        """Yield WAV chunks, degrading to the whole-utterance route (#12886, #13215).

        Prefers ``/tts/synthesize/stream`` so the caller can emit audio after
        the first ~250ms instead of after the whole clip. When the deployed
        worker predates that route it answers 404 *before* any chunk is sent,
        so falling back to ``/tts/synthesize`` here cannot duplicate or
        interleave audio — the fallback yields the whole clip as one chunk.

        Callers get one uniform contract regardless of how current the worker
        is, which is what keeps a worker/backend skew from turning into
        silence (WebSocket path) or a hard 404 (HTTP path).
        """
        emitted = False
        if not self._streaming_known_absent():
            try:
                async with aclosing(self.synthesize_stream(text, voice_id=voice_id, language=language)) as stream:
                    async for chunk in stream:
                        emitted = True
                        yield chunk
                return
            except TTSStreamUnsupported as e:
                if emitted:
                    raise  # cannot restart mid-utterance without repeating audio
                self._stream_absent_until = time.monotonic() + STREAM_PROBE_TTL
                logger.warning(
                    "TTS worker does not serve /tts/synthesize/stream (%s); using the "
                    "whole-utterance route for the next %ds",
                    e,
                    STREAM_PROBE_TTL,
                )
        yield await self.synthesize(text, voice_id=voice_id, language=language)

    async def clone_voice(self, text: str, reference_audio: bytes) -> bytes:
        """Send text + reference audio to TTS worker; returns WAV bytes."""
        timeout = aiohttp.ClientTimeout(total=SYNTHESIS_TIMEOUT)
        data = aiohttp.FormData()
        data.add_field("text", text)
        data.add_field(
            "reference_audio",
            reference_audio,
            filename="reference.wav",
            content_type="audio/wav",
        )
        client = get_http_client()
        async with client.tracked_request(
            "POST", f"{self.base_url}/tts/clone-voice", data=data, timeout=timeout
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"TTS worker error {resp.status}: {body}")
            return await resp.read()

    async def list_voices(self) -> list[dict]:
        """List available voice profiles from TTS worker."""
        timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT)
        try:
            client = get_http_client()
            async with client.tracked_request(
                "GET", f"{self.base_url}/voices", timeout=timeout, suppress_error_log=True
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.warning("Failed to list voices: %s", e)
        return []

    async def create_voice(self, name: str, audio_bytes: bytes, filename: str = "ref.wav") -> dict:
        """Create a voice profile from reference audio."""
        timeout = aiohttp.ClientTimeout(total=SYNTHESIS_TIMEOUT)
        data = aiohttp.FormData()
        data.add_field("name", name)
        data.add_field(
            "audio",
            audio_bytes,
            filename=filename,
            content_type="audio/wav",
        )
        client = get_http_client()
        async with client.tracked_request("POST", f"{self.base_url}/voices/create", data=data, timeout=timeout) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Voice create error {resp.status}: {body}")
            return await resp.json()

    async def delete_voice(self, voice_id: str) -> bool:
        """Delete a voice profile."""
        timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT)
        try:
            client = get_http_client()
            async with client.tracked_request(
                "DELETE", f"{self.base_url}/voices/{voice_id}", timeout=timeout, suppress_error_log=True
            ) as resp:
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
