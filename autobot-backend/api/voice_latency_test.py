# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Time-to-first-audio regression tests for the voice paths (#13215, #12886).

These tests *measure* time-to-first-byte rather than asserting that some
function was called. A fake TTS worker is driven through the real
``TTSClient`` (only the pooled HTTP layer is stubbed) so the timing reflects
the actual client + route code path:

* ``/tts/synthesize``        -- returns the whole WAV after ``SYNTH_SECONDS``.
* ``/tts/synthesize/stream`` -- emits ``CHUNK_COUNT`` framed mini-WAVs, one
  every ``CHUNK_SECONDS``, so the first is audible after 1/CHUNK_COUNT of the
  utterance.

Before #13215, ``/api/voice/synthesize`` always used the whole-blob route, so
time-to-first-byte equalled total synthesis time (measured 4.7-10.1s live).

The stale-worker test covers #12886 from the backend side: when the deployed
worker predates ``/tts/synthesize/stream``, the WebSocket voice path used to
turn the resulting 404 into a ``{"type": "error"}`` frame and no audio at all
-- the frontend only falls back to HTTP when the *socket* fails, never on a
per-utterance server error, so the reply was silently dropped.
"""

import asyncio
import base64
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketState

from api.voice import router as voice_router
from api.voice_stream import _stream_chunks_pipelined
from services.tts_client import TTSClient

SYNTH_SECONDS = 0.5
CHUNK_COUNT = 5
CHUNK_SECONDS = SYNTH_SECONDS / CHUNK_COUNT
WHOLE_WAV = b"RIFF" + b"w" * 64
STREAM_CHUNKS = [b"RIFF" + bytes([i]) * 16 for i in range(CHUNK_COUNT)]
STREAM_URL_SUFFIX = "/tts/synthesize/stream"


class _PacedStreamReader:
    """Feeds the worker's ``[4-byte length][WAV]`` framing one chunk per tick."""

    def __init__(self, chunks: list, delay: float) -> None:
        self._frames = [len(c).to_bytes(4, "big") + c for c in chunks]
        self._delay = delay
        self._buf = b""
        self._index = 0

    async def readexactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            if self._index >= len(self._frames):
                raise asyncio.IncompleteReadError(self._buf, n)
            await asyncio.sleep(self._delay)
            self._buf += self._frames[self._index]
            self._index += 1
        out, self._buf = self._buf[:n], self._buf[n:]
        return out


def _make_worker_http_client(*, serves_stream: bool) -> MagicMock:
    """Pooled-HTTP-client stub standing in for a TTS worker with real timing."""

    async def _slow_read() -> bytes:
        await asyncio.sleep(SYNTH_SECONDS)
        return WHOLE_WAV

    def _tracked_request(method, url, **kwargs):
        streaming = url.endswith(STREAM_URL_SUFFIX)
        resp = MagicMock()
        resp.status = 200 if (serves_stream or not streaming) else 404
        resp.text = AsyncMock(return_value="Not Found")
        resp.read = AsyncMock(side_effect=_slow_read)
        resp.content = _PacedStreamReader(STREAM_CHUNKS, CHUNK_SECONDS)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    client = MagicMock()
    client.tracked_request = MagicMock(side_effect=_tracked_request)
    return client


class _MockSecurityLayer:
    """Minimal security_layer stub that always permits."""

    def check_permission(self, role: str, permission: str) -> bool:
        return True

    def audit_log(self, *args, **kwargs) -> None:
        pass


class _FakeWebSocket:
    """Minimal WebSocket stand-in recording every JSON message sent."""

    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.sent: list = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    app.state.security_layer = _MockSecurityLayer()
    return app


async def _time_to_first_byte(app: FastAPI, payload: dict) -> tuple:
    """POST /api/voice/synthesize over raw ASGI; return (TTFB seconds, body).

    Starlette's ``TestClient`` buffers the whole response before returning, so
    it cannot observe time-to-first-byte at all -- driving the ASGI app
    directly is the only way to measure the thing this issue is about, and it
    still exercises the real route, form parsing and StreamingResponse.
    """
    encoded = urlencode(payload).encode("utf-8")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/voice/synthesize",
        "raw_path": b"/api/voice/synthesize",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"content-length", str(len(encoded)).encode("ascii")),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    sent = []
    started = time.monotonic()

    delivered = asyncio.Event()

    async def _receive():
        # First call delivers the body; every later call is starlette's
        # disconnect listener, which must block (as a live client would)
        # rather than spin -- the task group cancels it once the response
        # generator finishes.
        if delivered.is_set():
            await asyncio.Event().wait()
        delivered.set()
        return {"type": "http.request", "body": encoded, "more_body": False}

    async def _send(message):
        sent.append((time.monotonic() - started, message))

    await app(scope, _receive, _send)

    status = next(m["status"] for _, m in sent if m["type"] == "http.response.start")
    assert status == 200, f"unexpected status {status}"
    body = b""
    first_byte_at = None
    for elapsed, message in sent:
        if message["type"] != "http.response.body":
            continue
        piece = message.get("body", b"")
        if piece and first_byte_at is None:
            first_byte_at = elapsed
        body += piece
    return first_byte_at, body


@pytest.mark.asyncio
async def test_streaming_synthesize_reaches_first_audio_far_sooner():
    """Measured: the streaming route must beat the whole-blob route to first audio.

    Regression guard for #13215 -- a naive "it called synthesize_stream"
    assertion would still pass if the route buffered the whole utterance
    before responding, which is exactly the defect.
    """
    app = _make_app()
    http_client = _make_worker_http_client(serves_stream=True)

    with patch("services.tts_client.get_http_client", return_value=http_client):
        with patch("api.voice.get_tts_client", return_value=TTSClient()):
            blocking_ttfb, blocking_body = await _time_to_first_byte(app, {"text": "hi", "user_role": "user"})
            streaming_ttfb, streaming_body = await _time_to_first_byte(
                app, {"text": "hi", "user_role": "user", "stream": "true"}
            )

    assert blocking_body == WHOLE_WAV
    assert streaming_body  # framed chunks
    assert blocking_ttfb >= SYNTH_SECONDS * 0.8, f"blocking TTFB {blocking_ttfb:.3f}s -- fake worker not pacing"
    assert streaming_ttfb < blocking_ttfb / 2, (
        f"streaming time-to-first-audio {streaming_ttfb:.3f}s is not materially "
        f"better than blocking {blocking_ttfb:.3f}s"
    )


@pytest.mark.asyncio
async def test_streaming_response_carries_every_chunk_in_order():
    """The framed body must decode back to the worker's chunks, losing none."""
    app = _make_app()
    http_client = _make_worker_http_client(serves_stream=True)

    with patch("services.tts_client.get_http_client", return_value=http_client):
        with patch("api.voice.get_tts_client", return_value=TTSClient()):
            _, body = await _time_to_first_byte(app, {"text": "hi", "user_role": "user", "stream": "true"})

    decoded, offset = [], 0
    while offset < len(body):
        size = int.from_bytes(body[offset : offset + 4], "big")
        offset += 4
        decoded.append(body[offset : offset + size])
        offset += size
    assert decoded == STREAM_CHUNKS


def test_non_streaming_synthesize_still_returns_a_single_wav():
    """Existing callers keep the audio/wav whole-blob contract (no opt-in flag)."""
    app = _make_app()
    client = TestClient(app)
    http_client = _make_worker_http_client(serves_stream=True)

    with patch("services.tts_client.get_http_client", return_value=http_client):
        with patch("api.voice.get_tts_client", return_value=TTSClient()):
            response = client.post("/api/voice/synthesize", data={"text": "hi", "user_role": "user"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == WHOLE_WAV


@pytest.mark.asyncio
async def test_ws_path_still_speaks_when_worker_lacks_stream_route():
    """A worker predating /tts/synthesize/stream must not silence the WS path (#12886).

    Previously ``_stream_chunks_pipelined`` let the 404 surface as an ``error``
    frame with zero ``tts_audio`` frames; the frontend logs that and plays
    nothing, so the whole reply was lost.
    """
    ws = _FakeWebSocket()
    http_client = _make_worker_http_client(serves_stream=False)

    with patch("services.tts_client.get_http_client", return_value=http_client):
        with patch("api.voice_stream.get_tts_client", return_value=TTSClient()):
            await _stream_chunks_pipelined(ws, "hello", asyncio.Event(), voice_id="alba")

    types = [m["type"] for m in ws.sent]
    assert "error" not in types, f"stale worker still surfaced an error frame: {ws.sent}"
    audio = [m for m in ws.sent if m["type"] == "tts_audio"]
    assert audio, "stale worker produced no audio at all"
    assert base64.b64decode(audio[0]["data"]) == WHOLE_WAV
    assert types[0] == "tts_start" and types[-1] == "tts_end"
