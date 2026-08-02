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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.tts_client import STREAM_PROBE_TTL, TTSClient


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
        with pytest.raises(RuntimeError):
            async for _ in tts_client.stream_or_synthesize("hello"):
                pass

    assert not any(u.endswith(BLOCKING_URL_SUFFIX) for u in mock_client.requested_urls)
