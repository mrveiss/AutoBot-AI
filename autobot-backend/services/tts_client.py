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
import io
import time
import wave
from collections.abc import AsyncIterator
from contextlib import aclosing

import aiohttp

from autobot_shared.env_utils import blank_to_none
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.metrics.tts import REALTIME_FACTOR_FLOOR
from autobot_shared.ssot_config import config, get_config
from autobot_shared.ssot_constants import TTL_5_MINUTES

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


def _wav_duration_seconds(wav_bytes: bytes) -> float:
    """Return the playable length of a WAV payload, or 0.0 if it cannot be read.

    Used to measure synthesis throughput (#12460). The worker's streamed chunks
    are complete mini-WAVs, so each one carries the header this needs. Anything
    unparseable contributes nothing rather than raising: telemetry must never be
    able to break audio delivery.
    """
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            frame_rate = wav.getframerate()
            if frame_rate <= 0:
                return 0.0
            return wav.getnframes() / float(frame_rate)
    except Exception:
        logger.debug("Unparseable WAV payload; excluded from throughput", exc_info=True)
        return 0.0


class _SynthesisThroughput:
    """Audio produced vs the time the worker spent producing it (#12460).

    Time-to-first-audio was fixed in #13215, but a worker that then sustains
    below real time starves the player and stutters anyway. The real-time factor
    is the number that separates those two failures, and nothing was recording
    it, so a worker running at 0.2x looked healthy on every dashboard.

    Only the intervals the worker is actually generating in are counted. This
    is an async generator feeding a WebSocket and a StreamingResponse, so it is
    suspended at each ``yield`` for as long as the consumer takes to forward the
    chunk. Billing that back-pressure to the worker would fire the
    below-real-time alert against a healthy one whenever a client is slow.
    """

    def __init__(self, route: str) -> None:
        self.route = route
        self._producing_seconds = 0.0
        self._audio_seconds = 0.0
        self._first_chunk_seconds: float | None = None
        self._first_chunk_audio = 0.0
        self._chunks = 0
        self._mark: float | None = None

    def start(self) -> None:
        """Open a production interval — before a request, and after each yield."""
        self._mark = time.monotonic()

    def observe(self, wav_bytes: bytes) -> None:
        """Close the production interval this payload arrived on."""
        if self._mark is not None:
            self._producing_seconds += time.monotonic() - self._mark
            self._mark = None
        duration = _wav_duration_seconds(wav_bytes)
        self._chunks += 1
        if self._first_chunk_seconds is None:
            # The first interval is connect + upload + model warm-up, not
            # generation rate. It is time-to-first-audio, and it is reported as
            # exactly that below rather than folded into the factor.
            self._first_chunk_seconds = self._producing_seconds
            self._first_chunk_audio = duration
        self._audio_seconds += duration

    def report(self) -> None:
        """Emit the metrics and warn when the worker ran below real time.

        A synthesis that produced no measurable audio (cancelled before the
        first chunk, or an unparseable payload) carries no rate and is skipped
        rather than recorded as a 0.0x outlier.
        """
        # Steady-state rate: drop the warm-up interval and the audio it produced,
        # so this measures the same thing the client's pre-roll measures. A
        # single-chunk synthesis (the whole-utterance route) has no steady state
        # to isolate, so its one interval is the only rate available.
        if self._chunks > 1 and self._first_chunk_seconds is not None:
            audio_seconds = self._audio_seconds - self._first_chunk_audio
            wall_seconds = self._producing_seconds - self._first_chunk_seconds
        else:
            audio_seconds = self._audio_seconds
            wall_seconds = self._producing_seconds
        # Latency telemetry stands on its own — a payload we could not measure
        # the duration of still tells us how long the caller waited.
        if self._first_chunk_seconds is not None:
            self._record_first_chunk(self._first_chunk_seconds)
        if audio_seconds <= 0 or wall_seconds <= 0:
            return
        try:
            # Lazy import to avoid a circular dependency with prometheus_metrics.
            from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

            metrics = get_metrics_manager()
            metrics.record_tts_synthesis(self.route, audio_seconds, wall_seconds)
        except Exception:
            logger.debug("TTS throughput metrics unavailable", exc_info=True)
        factor = audio_seconds / wall_seconds
        if factor < REALTIME_FACTOR_FLOOR:
            logger.warning(
                "TTS synthesis ran below real time: %.2fx (%.1fs of audio in %.1fs via %s) — "
                "streamed playback drains faster than the worker fills it",
                factor,
                audio_seconds,
                wall_seconds,
                self.route,
            )

    def _record_first_chunk(self, seconds: float) -> None:
        """Report time-to-first-audio, independent of whether a rate was derived."""
        try:
            from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

            get_metrics_manager().record_tts_first_chunk(self.route, seconds)
        except Exception:
            logger.debug("TTS first-chunk metrics unavailable", exc_info=True)


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

        Throughput is measured across whichever route serves the utterance and
        reported once on exit (#12460) — including when a caller abandons the
        stream mid-utterance, since audio-produced over generation-time is still
        the worker's real rate. The clock covers only the intervals the worker
        is generating in: it starts after the capability probe has resolved, and
        restarts after each yield so a slow consumer is not billed to the worker.
        """
        throughput = _SynthesisThroughput("stream")
        try:
            emitted = False
            if not self._streaming_known_absent():
                degraded = self._stream_absent_until > 0.0
                try:
                    throughput.start()
                    async with aclosing(self.synthesize_stream(text, voice_id=voice_id, language=language)) as stream:
                        async for chunk in stream:
                            if not emitted and degraded:
                                # Recovery is otherwise silent, leaving an operator
                                # unable to tell which route is in use (#13215 review).
                                logger.info("TTS worker now serves /tts/synthesize/stream; streaming resumed")
                                self._stream_absent_until = 0.0
                            emitted = True
                            throughput.observe(chunk)
                            yield chunk
                            throughput.start()
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
            throughput.route = "blob"
            throughput.start()
            whole = await self.synthesize(text, voice_id=voice_id, language=language)
            throughput.observe(whole)
            yield whole
        finally:
            throughput.report()

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
