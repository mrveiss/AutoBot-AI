# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Characterization of the backend <-> TTS worker wire contract (#17778).

Pins what ``TTSClient`` sends to the worker and what it hands back: the route
(blob vs stream), the form fields, that ``voice_id``/``language`` are OMITTED
rather than sent empty, that returned bytes are untouched (same WAV header, same
format), and the ``[4-byte big-endian length][WAV]`` stream framing.

NOT pinned here: the sample rate the worker itself produces. That lives in the
worker (``autobot-tts-worker``), outside this process; the fixture WAV is a
stand-in whose format is deliberately not 16 kHz. This file therefore proves the
client does not alter audio, not what the worker emits.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import create_autospec, patch
from urllib.parse import parse_qs

import pytest

from autobot_shared.audio_params import AudioFormat, describe_wav
from autobot_shared.http_client_manager import HTTPClientManager
from services.tts_client import SYNTHESIS_TIMEOUT, TTSClient

BASE = "http://tts-worker.invalid"
FIXTURE_WAV_FORMAT = AudioFormat(sample_rate=24_000, channels=1, sample_width=2, container="wav")
WAV_HEADER_BYTES = 44


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data, self._pos = data, 0

    async def readexactly(self, n: int) -> bytes:
        if self._pos + n > len(self._data):
            partial, self._pos = self._data[self._pos :], len(self._data)
            raise asyncio.IncompleteReadError(partial, n)
        chunk = self._data[self._pos : self._pos + n]
        self._pos += n
        return chunk


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status, self._body, self.content = status, body, _Reader(body)

    async def read(self) -> bytes:
        return self._body

    async def text(self) -> str:
        return "error body"


class RecordingHttp:
    """Autospec'd shared HTTP client that records each request it is asked to make."""

    def __init__(self, *responses: _Response) -> None:
        self.requests: list[dict] = []
        self._responses = list(responses)
        self.mock = create_autospec(HTTPClientManager, instance=True, spec_set=True)
        self.mock.tracked_request.side_effect = self._tracked

    @asynccontextmanager
    async def _tracked(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        yield self._responses.pop(0)

    def form(self, index: int = 0) -> dict[str, list[str]]:
        payload = self.requests[index]["data"]()
        return parse_qs(payload.decode(), keep_blank_values=True)


def _client(http: RecordingHttp):
    return patch("services.tts_client.get_http_client", return_value=http.mock)


def _frame(*chunks: bytes) -> bytes:
    return b"".join(len(c).to_bytes(4, "big") + c for c in chunks)


@pytest.mark.asyncio
async def test_synthesize_posts_to_the_blob_route_and_returns_the_bytes_untouched(fixture_wav) -> None:
    http = RecordingHttp(_Response(fixture_wav))
    with _client(http):
        result = await TTSClient(BASE).synthesize("hello", voice_id="alba", language="en")
    request = http.requests[0]
    assert (request["method"], request["url"]) == ("POST", f"{BASE}/tts/synthesize")
    assert request["timeout"].total == SYNTHESIS_TIMEOUT == 60.0
    assert result == fixture_wav
    assert result[:WAV_HEADER_BYTES] == fixture_wav[:WAV_HEADER_BYTES]
    assert describe_wav(result) == FIXTURE_WAV_FORMAT


@pytest.mark.asyncio
async def test_synthesize_sends_text_voice_id_and_language_as_form_fields(fixture_wav) -> None:
    http = RecordingHttp(_Response(fixture_wav))
    with _client(http):
        await TTSClient(BASE).synthesize("hello", voice_id="alba", language="en")
    assert http.form() == {"text": ["hello"], "voice_id": ["alba"], "language": ["en"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, {"text": ["hello"]}),
        ({"voice_id": "alba"}, {"text": ["hello"], "voice_id": ["alba"]}),
        ({"language": "lv"}, {"text": ["hello"], "language": ["lv"]}),
    ],
)
async def test_empty_voice_id_and_language_are_omitted_not_sent_blank(fixture_wav, kwargs, expected) -> None:
    http = RecordingHttp(_Response(fixture_wav))
    with _client(http):
        await TTSClient(BASE).synthesize("hello", **kwargs)
    assert http.form() == expected


@pytest.mark.asyncio
async def test_synthesize_raises_on_a_worker_error() -> None:
    http = RecordingHttp(_Response(b"", status=500))
    with _client(http), pytest.raises(RuntimeError, match="TTS worker error 500"):
        await TTSClient(BASE).synthesize("hello")


@pytest.mark.asyncio
async def test_stream_posts_to_the_stream_route_with_the_same_form_fields(fixture_wav) -> None:
    http = RecordingHttp(_Response(_frame(fixture_wav)))
    with _client(http):
        _ = [c async for c in TTSClient(BASE).synthesize_stream("hi", voice_id="alba", language="en")]
    request = http.requests[0]
    assert (request["method"], request["url"]) == ("POST", f"{BASE}/tts/synthesize/stream")
    assert request["timeout"].total == 60.0
    assert http.form() == {"text": ["hi"], "voice_id": ["alba"], "language": ["en"]}


@pytest.mark.asyncio
async def test_stream_omits_empty_voice_id_and_language(fixture_wav) -> None:
    http = RecordingHttp(_Response(_frame(fixture_wav)))
    with _client(http):
        _ = [c async for c in TTSClient(BASE).synthesize_stream("hi")]
    assert http.form() == {"text": ["hi"]}


@pytest.mark.asyncio
async def test_stream_yields_each_length_prefixed_wav_unchanged(make_wav) -> None:
    chunks = [make_wav(frames=240), make_wav(frames=480), make_wav(frames=120)]
    http = RecordingHttp(_Response(_frame(*chunks)))
    with _client(http):
        received = [c async for c in TTSClient(BASE).synthesize_stream("hi")]
    assert received == chunks
    assert all(describe_wav(c) == FIXTURE_WAV_FORMAT for c in received)
    assert [c[:WAV_HEADER_BYTES][:4] for c in received] == [b"RIFF"] * 3


@pytest.mark.asyncio
async def test_the_stream_length_prefix_is_four_bytes_big_endian(make_wav) -> None:
    chunk = make_wav(frames=300)
    assert len(chunk) > 255  # a length that needs the second byte tells big from little endian
    http = RecordingHttp(_Response(len(chunk).to_bytes(4, "little") + chunk))
    with _client(http), pytest.raises(RuntimeError):
        _ = [c async for c in TTSClient(BASE).synthesize_stream("hi")]


@pytest.mark.asyncio
async def test_a_worker_without_the_stream_route_falls_back_to_one_blob_chunk(fixture_wav) -> None:
    http = RecordingHttp(_Response(b"", status=404), _Response(fixture_wav))
    with _client(http):
        received = [c async for c in TTSClient(BASE).stream_or_synthesize("hi", voice_id="alba")]
    assert [r["url"] for r in http.requests] == [f"{BASE}/tts/synthesize/stream", f"{BASE}/tts/synthesize"]
    assert received == [fixture_wav]
