# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the voice_stream WebSocket streaming path (#12501).

Exercises ``_stream_chunks_pipelined`` (shared by ``speak`` and
``speak_sentence``) and ``_tts_queue_worker`` directly against a fake
WebSocket and a fake TTSClient.synthesize_stream, so no real worker/network
is required. Covers: multi-chunk forwarding, tts_start/tts_end framing,
barge-in (cancel_event) stopping mid-stream, and error propagation.
"""

import asyncio
import base64
import contextlib
from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketState

from api.voice_stream import _stream_chunks_pipelined, _tts_queue_worker


class _FakeWebSocket:
    """Minimal WebSocket stand-in recording every JSON message sent."""

    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


class _FakeTTSClient:
    """Stand-in for TTSClient exposing the chunk-stream entry points (#12501).

    ``stream_or_synthesize`` is what ``voice_stream`` calls since #13215/#12886
    (it degrades to the whole-utterance route on a stale worker); it shares the
    same generator here because these tests are about the WS framing, not the
    worker-capability fallback -- that is covered in ``voice_latency_test``.
    """

    def __init__(self, chunks, cancel_event=None, cancel_after=None, closed_flag=None) -> None:
        self._chunks = chunks
        self._cancel_event = cancel_event
        self._cancel_after = cancel_after
        self._closed_flag = closed_flag

    def synthesize_stream(self, text: str, voice_id: str = "", language: str = ""):
        return self._gen()

    def stream_or_synthesize(self, text: str, voice_id: str = "", language: str = ""):
        return self._gen()

    async def _gen(self):
        try:
            for i, chunk in enumerate(self._chunks):
                yield chunk
                if self._cancel_event is not None and self._cancel_after is not None and i + 1 == self._cancel_after:
                    self._cancel_event.set()
        finally:
            if self._closed_flag is not None:
                self._closed_flag["closed"] = True


class TestStreamChunksPipelined:
    @pytest.mark.asyncio
    async def test_forwards_each_chunk_and_sends_tts_end(self):
        ws = _FakeWebSocket()
        chunks = [b"wav-1", b"wav-2", b"wav-3"]
        fake_client = _FakeTTSClient(chunks)

        with patch("api.voice_stream.get_tts_client", return_value=fake_client):
            await _stream_chunks_pipelined(ws, "hello world", asyncio.Event())

        types = [m["type"] for m in ws.sent]
        assert types == ["tts_start", "tts_audio", "tts_audio", "tts_audio", "tts_end"]

        audio_msgs = [m for m in ws.sent if m["type"] == "tts_audio"]
        assert [m["chunk"] for m in audio_msgs] == [1, 2, 3]
        assert base64.b64decode(audio_msgs[0]["data"]) == b"wav-1"
        assert base64.b64decode(audio_msgs[2]["data"]) == b"wav-3"

    @pytest.mark.asyncio
    async def test_empty_text_sends_start_and_end_only_no_worker_call(self):
        ws = _FakeWebSocket()

        with patch("api.voice_stream.get_tts_client") as mock_get_client:
            await _stream_chunks_pipelined(ws, "", asyncio.Event())

        assert [m["type"] for m in ws.sent] == ["tts_start", "tts_end"]
        mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_barge_in_cancel_event_stops_mid_stream_and_closes_generator(self):
        """cancel_event set mid-stream stops forwarding further chunks and
        aclosing() tears down the worker's HTTP stream (#1527, #12501)."""
        ws = _FakeWebSocket()
        cancel_event = asyncio.Event()
        chunks = [b"wav-1", b"wav-2", b"wav-3", b"wav-4"]
        closed_flag = {"closed": False}
        fake_client = _FakeTTSClient(chunks, cancel_event=cancel_event, cancel_after=2, closed_flag=closed_flag)

        with patch("api.voice_stream.get_tts_client", return_value=fake_client):
            await _stream_chunks_pipelined(ws, "hello world", cancel_event)

        audio_msgs = [m for m in ws.sent if m["type"] == "tts_audio"]
        assert len(audio_msgs) == 2  # chunks 3 and 4 never sent
        assert ws.sent[-1]["type"] == "tts_end"
        assert closed_flag["closed"] is True

    @pytest.mark.asyncio
    async def test_synthesis_error_sends_error_and_still_sends_tts_end(self):
        class _FailingClient:
            def stream_or_synthesize(self, text, voice_id="", language=""):
                async def _gen():
                    yield b"wav-1"
                    raise RuntimeError("worker exploded")

                return _gen()

        ws = _FakeWebSocket()
        with patch("api.voice_stream.get_tts_client", return_value=_FailingClient()):
            await _stream_chunks_pipelined(ws, "hello", asyncio.Event())

        types = [m["type"] for m in ws.sent]
        assert types == ["tts_start", "tts_audio", "error", "tts_end"]
        assert "worker exploded" in ws.sent[2]["message"]


class TestTtsQueueWorker:
    @pytest.mark.asyncio
    async def test_speak_sentence_forwards_chunks_and_tts_end(self):
        ws = _FakeWebSocket()
        chunks = [b"wav-1", b"wav-2"]
        fake_client = _FakeTTSClient(chunks)
        cancel_event = asyncio.Event()
        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(("hello", "alba", "en"))

        with patch("api.voice_stream.get_tts_client", return_value=fake_client):
            worker_task = asyncio.create_task(_tts_queue_worker(ws, queue, cancel_event))
            for _ in range(50):
                if any(m["type"] == "tts_end" for m in ws.sent):
                    break
                await asyncio.sleep(0.01)
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task

        assert [m["type"] for m in ws.sent] == ["tts_start", "tts_audio", "tts_audio", "tts_end"]
