# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for TTSClient.synthesize_stream (#12501).

Mocks aiohttp.ClientSession so no real network/worker is required — same
pattern as tests/utils/test_traced_http_client.py. Exercises the client
side of the worker's length-prefixed streaming wire format:
``[4-byte big-endian length][WAV bytes]`` repeated back to back.
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


def _make_mock_session(body: bytes, status: int = 200) -> MagicMock:
    """Return a MagicMock standing in for aiohttp.ClientSession with one POST response."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.content = _FakeStreamReader(body)
    mock_resp.text = AsyncMock(return_value="error body")

    mock_post_cm = MagicMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_post_cm)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.mark.asyncio
async def test_synthesize_stream_yields_multiple_chunks():
    """synthesize_stream yields each WAV chunk from the framed HTTP body in order."""
    chunks = [b"RIFF-chunk-one", b"RIFF-chunk-two", b"RIFF-chunk-three"]
    session = _make_mock_session(_framed(chunks))

    with patch("aiohttp.ClientSession", return_value=session):
        client = TTSClient()
        received = [c async for c in client.synthesize_stream("hello world", voice_id="alba")]

    assert received == chunks


@pytest.mark.asyncio
async def test_synthesize_stream_raises_on_non_200():
    """synthesize_stream raises RuntimeError when the worker returns a non-200 status."""
    session = _make_mock_session(b"", status=500)

    with patch("aiohttp.ClientSession", return_value=session):
        client = TTSClient()
        with pytest.raises(RuntimeError, match="TTS worker error 500"):
            async for _ in client.synthesize_stream("hello"):
                pass


@pytest.mark.asyncio
async def test_synthesize_stream_raises_on_truncated_chunk():
    """A length prefix promising more bytes than are sent raises, instead of silently truncating audio."""
    body = (100).to_bytes(4, "big") + b"short"
    session = _make_mock_session(body)

    with patch("aiohttp.ClientSession", return_value=session):
        client = TTSClient()
        with pytest.raises(RuntimeError, match="truncated mid-chunk"):
            async for _ in client.synthesize_stream("hello"):
                pass


@pytest.mark.asyncio
async def test_synthesize_stream_empty_body_yields_nothing():
    """An empty response body (zero chunks) yields nothing and does not raise."""
    session = _make_mock_session(b"")

    with patch("aiohttp.ClientSession", return_value=session):
        client = TTSClient()
        received = [c async for c in client.synthesize_stream("hello")]

    assert received == []
