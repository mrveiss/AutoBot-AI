# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A voice's reference audio reaches the TTS worker as WAV, and unusable audio is a 4xx (#18477)."""

from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
import wave
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from media.audio import reference_wav
from media.audio.reference_wav import UNSUPPORTED_AUDIO_CODE, is_wav, to_reference_wav


def _wav_bytes(seconds: float = 0.2, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01" * int(rate * seconds))
    return buf.getvalue()


def _fake_extract(produced: bytes):
    async def extract(path, output_path=None, sample_rate=0, channels=0, max_duration=None):
        out = path + ".out.wav"
        with open(out, "wb") as fh:
            fh.write(produced)
        return out

    return extract


@pytest.mark.asyncio
async def test_a_wav_passes_through_unchanged_and_is_never_converted():
    data = _wav_bytes()
    with patch.object(reference_wav, "get_ffmpeg_service") as svc:
        assert await to_reference_wav(data, "ref.wav") is data
        assert await to_reference_wav(data, "whatever.m4a") is data  # judged by content, not by name
    svc.assert_not_called()


@pytest.mark.asyncio
async def test_an_m4a_is_converted_by_the_bounded_ffmpeg_service_and_comes_out_as_wav():
    converted = _wav_bytes(rate=24000)
    service = type("S", (), {"extract_audio": staticmethod(_fake_extract(converted))})()
    with patch.object(reference_wav, "get_ffmpeg_service", return_value=service):
        out = await to_reference_wav(b"\x00\x00\x00\x20ftypM4A not really aac", "memo.M4A")
    assert out == converted and is_wav(out)


@pytest.mark.asyncio
async def test_the_conversion_asks_for_mono_and_a_bounded_duration():
    seen = {}

    async def extract(path, output_path=None, sample_rate=0, channels=0, max_duration=None):
        seen.update(sample_rate=sample_rate, channels=channels, max_duration=max_duration)
        out = path + ".out.wav"
        open(out, "wb").write(_wav_bytes())
        return out

    service = type("S", (), {"extract_audio": staticmethod(extract)})()
    with patch.object(reference_wav, "get_ffmpeg_service", return_value=service):
        await to_reference_wav(b"x" * 64, "memo.m4a")
    assert seen["channels"] == 1 and seen["sample_rate"] == reference_wav.REFERENCE_SAMPLE_RATE
    assert seen["max_duration"] == reference_wav.REFERENCE_MAX_SECONDS


@pytest.mark.asyncio
async def test_audio_ffmpeg_cannot_decode_is_a_422_with_a_stable_code_not_a_500():
    service = type("S", (), {"extract_audio": AsyncMock(side_effect=RuntimeError("FFmpeg extraction failed: bad"))})()
    with patch.object(reference_wav, "get_ffmpeg_service", return_value=service):
        with pytest.raises(HTTPException) as caught:
            await to_reference_wav(b"garbage" * 10, "memo.m4a")
    assert caught.value.status_code == 422 and caught.value.detail["code"] == UNSUPPORTED_AUDIO_CODE


@pytest.mark.asyncio
async def test_an_extension_outside_the_allowlist_is_a_415_with_the_same_code():
    with pytest.raises(HTTPException) as caught:
        await to_reference_wav(b"MZ" * 20, "payload.exe")
    assert caught.value.status_code == 415 and caught.value.detail["code"] == UNSUPPORTED_AUDIO_CODE


@pytest.mark.asyncio
async def test_a_missing_converter_is_a_503_not_a_decode_error():
    service = type("S", (), {"extract_audio": AsyncMock(side_effect=RuntimeError("FFmpeg not found at ffmpeg."))})()
    with patch.object(reference_wav, "get_ffmpeg_service", return_value=service):
        with pytest.raises(HTTPException) as caught:
            await to_reference_wav(b"x" * 40, "memo.m4a")
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_a_converter_output_that_is_not_wav_is_rejected():
    service = type("S", (), {"extract_audio": staticmethod(_fake_extract(b"not a wav"))})()
    with patch.object(reference_wav, "get_ffmpeg_service", return_value=service):
        with pytest.raises(HTTPException) as caught:
            await to_reference_wav(b"x" * 40, "memo.m4a")
    assert caught.value.status_code == 422


# -- the route: what the worker is sent -------------------------------------------------------------------------


def _upload(data: bytes, name: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


@pytest.mark.asyncio
async def test_the_route_sends_the_worker_wav_for_an_m4a_and_the_wav_unchanged_for_a_wav():
    from api.voice import voice_create_api

    sent = []

    class Tts:
        async def create_voice(self, name, audio_bytes, filename):
            sent.append((audio_bytes, filename))
            return {"id": "v1", "name": name}

    converted = _wav_bytes(rate=24000)
    service = type("S", (), {"extract_audio": staticmethod(_fake_extract(converted))})()
    with (
        patch("api.voice.get_tts_client", return_value=Tts()),
        patch.object(reference_wav, "get_ffmpeg_service", return_value=service),
    ):
        await voice_create_api(name="n", audio=_upload(b"\x00\x00\x00\x20ftypM4A..", "memo.m4a"))
        original = _wav_bytes()
        await voice_create_api(name="n", audio=_upload(original, "ref.wav"))
    assert sent[0] == (converted, "ref.wav") and is_wav(sent[0][0])  # the m4a reached the worker as WAV
    assert sent[1] == (original, "ref.wav")  # the WAV is untouched


@pytest.mark.asyncio
async def test_the_route_answers_garbage_with_a_4xx_and_never_calls_the_worker():
    from api.voice import voice_create_api

    tts = AsyncMock()
    service = type("S", (), {"extract_audio": AsyncMock(side_effect=RuntimeError("FFmpeg extraction failed: bad"))})()
    with (
        patch("api.voice.get_tts_client", return_value=tts),
        patch.object(reference_wav, "get_ffmpeg_service", return_value=service),
    ):
        with pytest.raises(HTTPException) as caught:
            await voice_create_api(name="n", audio=_upload(b"garbage bytes", "memo.m4a"))
    assert 400 <= caught.value.status_code < 500 and caught.value.detail["code"] == UNSUPPORTED_AUDIO_CODE
    tts.create_voice.assert_not_called()


@pytest.mark.asyncio
async def test_a_worker_422_becomes_the_same_4xx():
    from api.voice import voice_create_api
    from services.tts_client import TTSReferenceAudioRejected

    tts = type("T", (), {"create_voice": AsyncMock(side_effect=TTSReferenceAudioRejected("Format not recognised"))})()
    with patch("api.voice.get_tts_client", return_value=tts):
        with pytest.raises(HTTPException) as caught:
            await voice_create_api(name="n", audio=_upload(_wav_bytes(), "ref.wav"))
    assert caught.value.status_code == 422 and caught.value.detail["code"] == UNSUPPORTED_AUDIO_CODE


@pytest.mark.asyncio
async def test_the_upload_size_cap_still_applies_before_any_conversion():
    from api.voice import voice_create_api

    with (
        patch("media.audio.upload_limits.max_upload_bytes", return_value=10),
        patch.object(reference_wav, "get_ffmpeg_service") as svc,
    ):
        with pytest.raises(HTTPException) as caught:
            await voice_create_api(name="n", audio=_upload(b"x" * 100, "memo.m4a"))
    assert caught.value.status_code == 413
    svc.assert_not_called()


# -- the real converter ---------------------------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
@pytest.mark.asyncio
async def test_the_real_ffmpeg_service_turns_a_generated_m4a_into_mono_wav(tmp_path):
    m4a = tmp_path / "tone.m4a"
    made = subprocess.run(  # noqa: S603  # fixed argv, generated sample
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5",
            "-ac",
            "2",
            "-c:a",
            "aac",
            str(m4a),
        ],
        capture_output=True,
        check=False,
    )
    if made.returncode != 0:
        pytest.skip("this ffmpeg build cannot encode AAC")
    out = await to_reference_wav(await asyncio.to_thread(m4a.read_bytes), "tone.m4a")
    assert is_wav(out)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getnchannels() == 1 and w.getframerate() == reference_wav.REFERENCE_SAMPLE_RATE and w.getnframes() > 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
@pytest.mark.asyncio
async def test_the_real_ffmpeg_service_rejects_garbage_with_a_422():
    with pytest.raises(HTTPException) as caught:
        await to_reference_wav(b"this is not audio at all" * 20, "memo.m4a")
    assert caught.value.status_code == 422


# -- the worker side and the client between them -----------------------------------------------------------------


def test_the_worker_template_answers_an_undecodable_reference_with_422_not_500():
    """The Jinja template cannot be imported, so pin the branch in `create_voice` by its text."""
    from pathlib import Path

    template = next(
        Path(__file__)
        .resolve()
        .parents[3]
        .glob("autobot-slm-backend/ansible/roles/tts-worker/templates/tts-worker.py.j2")
    )
    body = template.read_text(encoding="utf-8").split("async def create_voice", 1)[1].split("@app.delete", 1)[0]
    assert 'type(e).__name__ == "LibsndfileError"' in body and "HTTPException(422" in body
    assert body.index("HTTPException(422") < body.index("HTTPException(500")  # the 4xx branch comes first


@pytest.mark.asyncio
async def test_the_tts_client_turns_a_worker_422_into_the_typed_rejection_and_other_errors_stay_errors():
    from contextlib import asynccontextmanager

    from services.tts_client import TTSClient, TTSReferenceAudioRejected

    def client_for(status):
        resp = type("R", (), {"status": status, "text": AsyncMock(return_value="Format not recognised")})()

        @asynccontextmanager
        async def tracked_request(*a, **k):
            yield resp

        return type("H", (), {"tracked_request": staticmethod(tracked_request)})()

    tts = TTSClient.__new__(TTSClient)
    tts.base_url = "http://worker"
    with patch("services.tts_client.get_http_client", return_value=client_for(422)):
        with pytest.raises(TTSReferenceAudioRejected):
            await tts.create_voice("n", b"x", "ref.wav")
    with patch("services.tts_client.get_http_client", return_value=client_for(500)):
        with pytest.raises(RuntimeError) as caught:
            await tts.create_voice("n", b"x", "ref.wav")
    assert not isinstance(caught.value, TTSReferenceAudioRejected)
