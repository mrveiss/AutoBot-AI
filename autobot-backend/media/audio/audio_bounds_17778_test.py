# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bounds on the upload decode path: cancel kills ffmpeg, caps on bytes, seconds and output (#17778)."""

import asyncio
import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from media.audio import decode
from media.audio.ffmpeg_service import FFmpegService, _communicate_bounded
from media.audio.upload_limits import read_capped_audio


class _HangingProcess:
    """An ffmpeg stand-in whose communicate() never finishes."""

    def __init__(self):
        self.killed = False
        self.reaped = False

    async def communicate(self):
        await asyncio.sleep(3600)

    def kill(self):
        self.killed = True

    async def wait(self):
        self.reaped = True


@pytest.mark.asyncio
async def test_cancel_kills_and_reaps_ffmpeg_and_reraises():
    process = _HangingProcess()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_communicate_bounded(process), timeout=0.05)
    assert process.killed and process.reaped


@pytest.mark.asyncio
async def test_own_timeout_still_kills_and_reaps():
    process = _HangingProcess()
    with patch("media.audio.ffmpeg_service.FFMPEG_TIMEOUT_SECONDS", 0.05):
        with pytest.raises(RuntimeError, match="timed out"):
            await _communicate_bounded(process)
    assert process.killed and process.reaped


@pytest.fixture
def webm_file(tmp_path):
    src = tmp_path / "a.webm"
    src.write_bytes(b"x")
    return src


@pytest.mark.asyncio
async def test_max_duration_becomes_a_t_flag_and_is_absent_otherwise(webm_file, tmp_path):
    src = webm_file
    proc = MagicMock(returncode=0)
    proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as spawn:
        await FFmpegService().extract_audio(str(src), str(tmp_path / "o.wav"), max_duration=601.0)
        assert spawn.call_args.args[spawn.call_args.args.index("-t") + 1] == "601"
        await FFmpegService().extract_audio(str(src), str(tmp_path / "o.wav"))
        assert "-t" not in spawn.call_args.args


class _Upload:
    # Every real caller hands over a FastAPI UploadFile, which always has .filename; the audio routes that
    # need one (clone/create/process-audio) send an audio-typed name, so the fake sends one too (#19088).
    filename = "clip.wav"

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    async def read(self, size=-1):
        return self._buf.read(size)


@pytest.mark.asyncio
async def test_upload_over_the_byte_cap_is_413_and_under_it_is_read(monkeypatch):
    monkeypatch.setenv("AUTOBOT_AUDIO_UPLOAD_MAX_BYTES", "10")
    with pytest.raises(HTTPException) as caught:
        await read_capped_audio(_Upload(b"x" * 11))
    assert caught.value.status_code == 413
    assert await read_capped_audio(_Upload(b"x" * 10)) == b"x" * 10


def _wav_file(path, seconds: int, rate: int = 16000) -> str:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * rate * seconds)
    return str(path)


def test_output_over_the_byte_cap_is_refused_before_reading(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOBOT_AUDIO_DECODE_MAX_OUTPUT_BYTES", "1000")
    path = _wav_file(tmp_path / "o.wav", 1)
    with pytest.raises(ValueError, match="byte cap"):
        decode._check_output_bounds(path, 16000, 600.0)


def test_output_longer_than_the_duration_cap_is_refused(tmp_path):
    path = _wav_file(tmp_path / "o.wav", 3)
    with pytest.raises(ValueError, match="cap"):
        decode._check_output_bounds(path, 16000, 2.0)
    decode._check_output_bounds(path, 16000, 5.0)


@pytest.mark.asyncio
async def test_transcode_passes_the_duration_cap_to_ffmpeg_and_reports_undecodable(monkeypatch):
    monkeypatch.setenv("AUTOBOT_AUDIO_DECODE_MAX_SECONDS", "30")
    service = MagicMock()
    service.extract_audio = AsyncMock(side_effect=lambda i, o, **kw: _wav_file(o, 40))
    with patch.object(decode, "get_ffmpeg_service", return_value=service):
        with pytest.raises(ValueError, match=decode.UNDECODABLE_MESSAGE):
            await decode._transcode_then_decode(b"OggS" + b"\0" * 8, 16000)
    assert service.extract_audio.call_args.kwargs["max_duration"] == 31.0
