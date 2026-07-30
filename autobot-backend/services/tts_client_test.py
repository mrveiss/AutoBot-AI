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

from services.tts_client import TTSClient


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
