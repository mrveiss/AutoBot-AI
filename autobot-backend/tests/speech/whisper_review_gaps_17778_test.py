# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Slice-2 review gaps (#17778): off-loop route load, inference lock, ffmpeg timeout, narrow catch."""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, create_autospec

import numpy as np
import pytest

import media.audio.decode as decode
import media.audio.ffmpeg_service as ffmpeg_service
import media.audio.pipeline as audio_pipeline

WEBM_BYTES = b"\x1a\x45\xdf\xa3" + b"\x00" * 32


class _AsrPipeline:
    def __call__(self, inputs, *, return_timestamps=None, generate_kwargs=None):
        raise NotImplementedError


# ── route: the model load is off the event loop ───────────────────────────────


@pytest.mark.asyncio
async def test_the_route_loads_the_model_in_a_worker_thread(monkeypatch) -> None:
    from api.voice import TranscriptionFailed, _transcribe_with_whisper

    seen = {}

    def slow_loader():
        seen["thread"] = threading.get_ident()
        time.sleep(0.05)
        return None

    monkeypatch.setattr(audio_pipeline, "get_whisper_pipeline", slow_loader)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.005)
            ticks += 1

    task = asyncio.create_task(ticker())
    with pytest.raises(TranscriptionFailed):
        await _transcribe_with_whisper(b"x", "audio/wav", "")
    task.cancel()
    assert seen["thread"] != threading.get_ident()
    assert ticks >= 3, "the event loop was blocked while the model loaded"


# ── inference lock ────────────────────────────────────────────────────────────


def test_concurrent_calls_never_overlap_inside_the_pipeline() -> None:
    state = {"inside": 0, "max": 0}
    guard = threading.Lock()

    def fake_pipe(inputs, *, return_timestamps=None, generate_kwargs=None):
        with guard:
            state["inside"] += 1
            state["max"] = max(state["max"], state["inside"])
        time.sleep(0.05)
        with guard:
            state["inside"] -= 1
        return {"text": "hi"}

    pipe = create_autospec(_AsrPipeline, instance=True, spec_set=True)
    pipe.side_effect = fake_pipe
    samples = np.zeros(1600, dtype=np.float32)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(audio_pipeline.transcribe_array, pipe, samples, 16_000) for _ in range(2)]
        assert [f.result().text for f in futures] == ["hi", "hi"]
    assert state["max"] == 1


# ── ffmpeg timeout ────────────────────────────────────────────────────────────


class _NeverFinishes:
    """A process whose communicate() never completes; records kill/wait."""

    def __init__(self):
        self.mock = create_autospec(asyncio.subprocess.Process, instance=True, spec_set=True)
        self.mock.communicate = AsyncMock(side_effect=self._hang)
        self.mock.wait = AsyncMock(return_value=-9)

    @staticmethod
    async def _hang():
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_a_hung_ffmpeg_is_killed_reaped_and_reported_sanitized(monkeypatch, tmp_path) -> None:
    proc = _NeverFinishes()
    monkeypatch.setattr(ffmpeg_service, "FFMPEG_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc.mock))
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    with pytest.raises(ValueError) as caught:
        await decode.decode_audio_bytes_async(WEBM_BYTES)
    assert str(caught.value) == decode.UNDECODABLE_MESSAGE
    proc.mock.kill.assert_called_once_with()
    proc.mock.wait.assert_awaited_once_with()
    assert list(tmp_path.iterdir()) == [], "temp files leaked after the timeout"


def test_the_ffmpeg_timeout_is_env_backed() -> None:
    from autobot_shared.env_registry import REGISTRY

    assert "AUTOBOT_FFMPEG_TIMEOUT_SECONDS" in REGISTRY


# ── the transcode catch is narrow ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_programming_error_in_the_transcode_propagates(monkeypatch) -> None:
    service = create_autospec(ffmpeg_service.FFmpegService, instance=True, spec_set=True)
    service.extract_audio.side_effect = TypeError("bug")
    monkeypatch.setattr(decode, "get_ffmpeg_service", lambda: service)
    with pytest.raises(TypeError, match="bug"):
        await decode.decode_audio_bytes_async(WEBM_BYTES)
