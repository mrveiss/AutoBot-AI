# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for TTSClient.synthesize_stream (#12501).

Mocks the shared pooled HTTP client so no real network/worker is required.
Exercises the client side of the worker's length-prefixed streaming wire
format: ``[4-byte big-endian length][WAV bytes]`` repeated back to back.

Issue #12979 moved TTSClient off per-request ``aiohttp.ClientSession`` onto
``autobot_shared.http_client``. The seam is now
``get_http_client().tracked_request(method, url, **kwargs)``, which yields the
response, so the stub targets that entry point instead of ``aiohttp.ClientSession``
-- patching the latter would no longer intercept anything and the test would
dial out for real.
"""

import asyncio
import io
import logging
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.tts_client import STREAM_PROBE_TTL, TTSClient, _wav_duration_seconds


class _FakeStreamReader:
    """Minimal stand-in for aiohttp.StreamReader.readexactly over a fixed buffer."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    async def readexactly(self, n: int) -> bytes:
        if self._pos + n > len(self._data):
            partial = self._data[self._pos :]
            self._pos = len(self._data)
            raise asyncio.IncompleteReadError(partial, n)
        chunk = self._data[self._pos : self._pos + n]
        self._pos += n
        return chunk


def _framed(chunks: list) -> bytes:
    """Build the worker's length-prefixed wire format for a list of WAV chunks."""
    out = b""
    for c in chunks:
        out += len(c).to_bytes(4, "big") + c
    return out


def _make_mock_http_client(body: bytes, status: int = 200) -> MagicMock:
    """Return a MagicMock standing in for the shared pooled HTTP client.

    ``get_http_client().tracked_request(...)`` is an ``@asynccontextmanager``
    call, so the mock's return value must itself be the async context manager
    (``__aenter__``/``__aexit__``) that yields the response -- ``tracked_request``
    is not awaited by callers, only entered via ``async with``.
    """
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.content = _FakeStreamReader(body)
    mock_resp.text = AsyncMock(return_value="error body")

    mock_request_cm = MagicMock()
    mock_request_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_request_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.tracked_request = MagicMock(return_value=mock_request_cm)
    return mock_client


@pytest.mark.asyncio
async def test_synthesize_stream_yields_multiple_chunks():
    """synthesize_stream yields each WAV chunk from the framed HTTP body in order."""
    chunks = [b"RIFF-chunk-one", b"RIFF-chunk-two", b"RIFF-chunk-three"]
    mock_client = _make_mock_http_client(_framed(chunks))

    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        received = [c async for c in tts_client.synthesize_stream("hello world", voice_id="alba")]

    assert received == chunks


@pytest.mark.asyncio
async def test_synthesize_stream_raises_on_non_200():
    """synthesize_stream raises RuntimeError when the worker returns a non-200 status."""
    mock_client = _make_mock_http_client(b"", status=500)

    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        with pytest.raises(RuntimeError, match="TTS worker error 500"):
            async for _ in tts_client.synthesize_stream("hello"):
                pass


@pytest.mark.asyncio
async def test_synthesize_stream_raises_on_truncated_chunk():
    """A length prefix promising more bytes than are sent raises, instead of silently truncating audio."""
    body = (100).to_bytes(4, "big") + b"short"
    mock_client = _make_mock_http_client(body)

    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        with pytest.raises(RuntimeError, match="truncated mid-chunk"):
            async for _ in tts_client.synthesize_stream("hello"):
                pass


@pytest.mark.asyncio
async def test_synthesize_stream_empty_body_yields_nothing():
    """An empty response body (zero chunks) yields nothing and does not raise."""
    mock_client = _make_mock_http_client(b"")

    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        received = [c async for c in tts_client.synthesize_stream("hello")]

    assert received == []


# ---------------------------------------------------------------------------
# Stale-worker fallback + capability probe (#12886, #13215)
# ---------------------------------------------------------------------------

WHOLE_WAV = b"RIFF-whole-utterance"
STREAM_URL_SUFFIX = "/tts/synthesize/stream"
BLOCKING_URL_SUFFIX = "/tts/synthesize"


def _make_routing_http_client(responses: dict) -> MagicMock:
    """Mock pooled HTTP client that dispatches on the request URL.

    ``responses`` maps a URL suffix to ``(status, body)``. Every requested URL
    is recorded on ``mock_client.requested_urls`` so a test can assert that the
    stream route was (or was not) attempted -- that is what distinguishes a
    cached capability probe from a per-request round trip.
    """
    requested: list = []

    def _tracked_request(method, url, **kwargs):
        requested.append(url)
        status, body = next(
            ((s, b) for suffix, (s, b) in responses.items() if url.endswith(suffix)),
            (404, b""),
        )
        resp = MagicMock()
        resp.status = status
        resp.content = _FakeStreamReader(body)
        resp.text = AsyncMock(return_value="Not Found")
        resp.read = AsyncMock(return_value=body)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    client = MagicMock()
    client.tracked_request = MagicMock(side_effect=_tracked_request)
    client.requested_urls = requested
    return client


class _FakeClock:
    """Controllable stand-in for time.monotonic so the probe TTL is testable."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _stale_worker_client() -> MagicMock:
    """A worker that serves /tts/synthesize but 404s /tts/synthesize/stream."""
    return _make_routing_http_client(
        {
            STREAM_URL_SUFFIX: (404, b""),
            BLOCKING_URL_SUFFIX: (200, WHOLE_WAV),
        }
    )


@pytest.mark.asyncio
async def test_stream_or_synthesize_falls_back_when_worker_lacks_stream_route():
    """A worker predating /tts/synthesize/stream must still produce audio (#12886).

    The deployed worker 404s the streaming route while serving the whole-blob
    one. Before this fallback existed the caller got a RuntimeError and the
    user got silence.
    """
    mock_client = _stale_worker_client()
    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        received = [c async for c in tts_client.stream_or_synthesize("hello", voice_id="alba")]

    assert received == [WHOLE_WAV]
    assert any(u.endswith(STREAM_URL_SUFFIX) for u in mock_client.requested_urls)
    assert any(u.endswith(BLOCKING_URL_SUFFIX) for u in mock_client.requested_urls)


@pytest.mark.asyncio
async def test_stream_or_synthesize_caches_the_negative_probe():
    """After one 404 the stream route is not re-attempted on every utterance."""
    mock_client = _stale_worker_client()
    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        async for _ in tts_client.stream_or_synthesize("first"):
            pass
        mock_client.requested_urls.clear()
        received = [c async for c in tts_client.stream_or_synthesize("second")]

    assert received == [WHOLE_WAV]
    assert not any(u.endswith(STREAM_URL_SUFFIX) for u in mock_client.requested_urls)


@pytest.mark.asyncio
async def test_stream_or_synthesize_reprobes_after_ttl():
    """A worker updated in place starts streaming again without a backend restart."""
    mock_client = _stale_worker_client()
    clock = _FakeClock()
    with (
        patch("services.tts_client.get_http_client", return_value=mock_client),
        patch("services.tts_client.time.monotonic", clock),
    ):
        tts_client = TTSClient()
        async for _ in tts_client.stream_or_synthesize("first"):
            pass
        mock_client.requested_urls.clear()
        clock.now += STREAM_PROBE_TTL + 1
        async for _ in tts_client.stream_or_synthesize("second"):
            pass

    assert any(u.endswith(STREAM_URL_SUFFIX) for u in mock_client.requested_urls)


@pytest.mark.asyncio
async def test_stream_or_synthesize_streams_when_the_route_is_served():
    """A current worker streams: every chunk is yielded, the blocking route unused."""
    chunks = [b"RIFF-one", b"RIFF-two", b"RIFF-three"]
    mock_client = _make_routing_http_client({STREAM_URL_SUFFIX: (200, _framed(chunks))})
    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        received = [c async for c in tts_client.stream_or_synthesize("hello")]

    assert received == chunks
    assert not any(u.endswith(BLOCKING_URL_SUFFIX) for u in mock_client.requested_urls)


@pytest.mark.asyncio
async def test_stream_or_synthesize_does_not_mask_worker_failures():
    """A 500 is a real failure, not a contract skew -- it must not silently retry."""
    mock_client = _make_routing_http_client(
        {
            STREAM_URL_SUFFIX: (500, b""),
            BLOCKING_URL_SUFFIX: (200, WHOLE_WAV),
        }
    )
    with patch("services.tts_client.get_http_client", return_value=mock_client):
        tts_client = TTSClient()
        with pytest.raises(RuntimeError) as exc:
            async for _ in tts_client.stream_or_synthesize("hello"):
                pass

    # TTSStreamUnsupported subclasses RuntimeError, so pytest.raises alone would
    # also pass if a 500 were mistakenly treated as route skew. Pin the exact
    # type: only 404/405 may degrade to the blocking endpoint.
    assert type(exc.value) is RuntimeError
    assert not any(u.endswith(BLOCKING_URL_SUFFIX) for u in mock_client.requested_urls)


# ---------------------------------------------------------------------------
# Synthesis throughput telemetry (#12460)
# ---------------------------------------------------------------------------
#
# #13215 fixed time-to-first-audio; this is the next constraint. Once streaming
# starts, a worker that sustains below real time starves the player and the
# audio stutters. The real-time factor separates those two failures and nothing
# consumed it, so a worker running at 0.2x looked healthy everywhere.


def _real_wav(seconds: float, frame_rate: int = 24000) -> bytes:
    """Build a real, parseable mono 16-bit WAV of the given playable length."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(frame_rate)
        wav.writeframes(b"\x00\x00" * int(seconds * frame_rate))
    return buf.getvalue()


def test_wav_duration_seconds_reads_a_real_wav():
    """Chunk duration comes from the WAV header, so throughput is measurable."""
    assert _wav_duration_seconds(_real_wav(0.25)) == pytest.approx(0.25)


def test_wav_duration_seconds_returns_zero_for_unparseable_audio():
    """Telemetry must never be able to break audio delivery."""
    assert _wav_duration_seconds(b"not-a-wav-at-all") == 0.0


@pytest.mark.asyncio
async def test_stream_or_synthesize_warns_and_records_below_real_time(caplog):
    """A worker producing 1s of audio in 4s is recorded at 0.25x and warned about."""
    chunks = [_real_wav(0.5), _real_wav(0.5)]
    mock_client = _make_routing_http_client({STREAM_URL_SUFFIX: (200, _framed(chunks))})
    clock = _FakeClock()
    recorded: list = []

    def _advance_on_chunk(*_args, **_kwargs):
        # Step the clock on every read so the 1.0s of audio below measures as
        # having taken several wall-seconds to produce.
        clock.now += 2.0
        return clock.now

    metrics = MagicMock()
    metrics.record_tts_synthesis = MagicMock(side_effect=lambda *a: recorded.append(a))

    with (
        patch("services.tts_client.get_http_client", return_value=mock_client),
        patch("services.tts_client.time.monotonic", side_effect=_advance_on_chunk),
        patch(
            "autobot_shared.monitoring.prometheus_metrics.get_metrics_manager",
            return_value=metrics,
        ),
        caplog.at_level(logging.WARNING, logger="services.tts_client"),
    ):
        tts_client = TTSClient()
        received = [c async for c in tts_client.stream_or_synthesize("hello")]

    assert received == chunks
    assert len(recorded) == 1
    route, audio_seconds, wall_seconds = recorded[0]
    assert route == "stream"
    assert audio_seconds == pytest.approx(1.0)
    assert audio_seconds / wall_seconds < 1.0
    assert "below real time" in caplog.text


@pytest.mark.asyncio
async def test_stream_or_synthesize_does_not_warn_at_or_above_real_time(caplog):
    """A worker keeping up is recorded but must not raise a throughput warning."""
    chunks = [_real_wav(2.0)]
    mock_client = _make_routing_http_client({STREAM_URL_SUFFIX: (200, _framed(chunks))})
    clock = _FakeClock()
    metrics = MagicMock()

    def _advance_slightly(*_args, **_kwargs):
        clock.now += 0.25
        return clock.now

    with (
        patch("services.tts_client.get_http_client", return_value=mock_client),
        patch("services.tts_client.time.monotonic", side_effect=_advance_slightly),
        patch(
            "autobot_shared.monitoring.prometheus_metrics.get_metrics_manager",
            return_value=metrics,
        ),
        caplog.at_level(logging.WARNING, logger="services.tts_client"),
    ):
        tts_client = TTSClient()
        received = [c async for c in tts_client.stream_or_synthesize("hello")]

    assert received == chunks
    metrics.record_tts_synthesis.assert_called_once()
    assert "below real time" not in caplog.text


@pytest.mark.asyncio
async def test_stream_or_synthesize_skips_telemetry_when_no_audio_is_measurable():
    """Unparseable payloads carry no rate; they must not land as a 0.0x outlier."""
    mock_client = _make_routing_http_client({STREAM_URL_SUFFIX: (200, _framed([b"RIFF-not-real"]))})
    metrics = MagicMock()

    with (
        patch("services.tts_client.get_http_client", return_value=mock_client),
        patch(
            "autobot_shared.monitoring.prometheus_metrics.get_metrics_manager",
            return_value=metrics,
        ),
    ):
        tts_client = TTSClient()
        received = [c async for c in tts_client.stream_or_synthesize("hello")]

    assert received == [b"RIFF-not-real"]
    metrics.record_tts_synthesis.assert_not_called()


@pytest.mark.asyncio
async def test_stream_or_synthesize_labels_the_whole_utterance_route():
    """A stale worker's blob route is measured too, labelled 'blob' not 'stream'."""
    mock_client = _make_routing_http_client(
        {
            STREAM_URL_SUFFIX: (404, b""),
            BLOCKING_URL_SUFFIX: (200, _real_wav(1.0)),
        }
    )
    recorded: list = []
    metrics = MagicMock()
    metrics.record_tts_synthesis = MagicMock(side_effect=lambda *a: recorded.append(a))

    with (
        patch("services.tts_client.get_http_client", return_value=mock_client),
        patch(
            "autobot_shared.monitoring.prometheus_metrics.get_metrics_manager",
            return_value=metrics,
        ),
    ):
        tts_client = TTSClient()
        async for _ in tts_client.stream_or_synthesize("hello"):
            pass

    assert len(recorded) == 1
    assert recorded[0][0] == "blob"
    assert recorded[0][1] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_stream_or_synthesize_does_not_bill_consumer_backpressure_to_the_worker(caplog):
    """A slow consumer must not make a healthy worker look below real time.

    This is an async generator feeding a WebSocket and a StreamingResponse, so
    it sits suspended at each ``yield`` for as long as the client takes to
    forward the chunk. Here the worker produces 2.0s of audio in 1.0s (a healthy
    2.0x) while the consumer spends 20s forwarding it. Counting that consumer
    time would report 0.09x and fire TTSSynthesisBelowRealTime against a worker
    that is keeping up fine.
    """
    chunks = [_real_wav(1.0), _real_wav(1.0)]
    mock_client = _make_routing_http_client({STREAM_URL_SUFFIX: (200, _framed(chunks))})
    clock = _FakeClock()
    recorded: list = []

    def _monotonic() -> float:
        # Every read costs 0.5s, so each start()->observe() production interval
        # measures 0.5s: 1.0s of generation for 2.0s of audio.
        clock.now += 0.5
        return clock.now

    metrics = MagicMock()
    metrics.record_tts_synthesis = MagicMock(side_effect=lambda *a: recorded.append(a))

    with (
        patch("services.tts_client.get_http_client", return_value=mock_client),
        patch("services.tts_client.time.monotonic", _monotonic),
        patch(
            "autobot_shared.monitoring.prometheus_metrics.get_metrics_manager",
            return_value=metrics,
        ),
        caplog.at_level(logging.WARNING, logger="services.tts_client"),
    ):
        tts_client = TTSClient()
        async for _ in tts_client.stream_or_synthesize("hello"):
            clock.now += 10.0

    assert len(recorded) == 1
    _route, audio_seconds, wall_seconds = recorded[0]
    assert audio_seconds == pytest.approx(2.0)
    # 20s of consumer time excluded: the worker is recorded at its real 2.0x.
    assert audio_seconds / wall_seconds == pytest.approx(2.0)
    assert "below real time" not in caplog.text
