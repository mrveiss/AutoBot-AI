# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every REAL provider raises on failure and returns ``[]`` only for genuine silence (#17778).

The fallback chain treats a returned ``[]`` as "ran, heard nothing" and stops. A provider
that swallowed its own error and returned ``[]`` therefore ended the chain with an empty
transcript (Latvian without the LATE binary never reached Tilde). These tests use the real
provider classes; only the network/binary/engine edge is simulated.
"""

import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.http_client import get_http_client
from voice_processing.models import SpeechRecognitionResult
from voice_processing.providers import (
    ProviderFailed,
    ProviderRegistry,
    ProviderUnavailable,
    TranscriptionUnavailableError,
)
from voice_processing.providers.cloud.assemblyai_provider import AssemblyAIProvider
from voice_processing.providers.cloud.deepgram_provider import DeepgramProvider
from voice_processing.providers.cloud.google_provider import GoogleSpeechProvider
from voice_processing.providers.generic_provider import GenericProvider
from voice_processing.providers.lv.late_provider import LateProvider
from voice_processing.providers.lv.tilde_provider import TildeProvider


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"\x00" * 64)
    return str(path)


def _http(status=200, body=None, text=""):
    """A tracked_request replacement answering one canned response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body if body is not None else {})
    resp.text = AsyncMock(return_value=text)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return patch.object(get_http_client(), "tracked_request", return_value=resp)


def _transport_error():
    return patch.object(get_http_client(), "tracked_request", side_effect=ConnectionError("down"))


@pytest.fixture
def deepgram(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "k")
    return DeepgramProvider()


@pytest.fixture
def assemblyai(monkeypatch):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "k")
    return AssemblyAIProvider()


@pytest.fixture
def tilde():
    return TildeProvider(api_key="k", api_url="https://asr.invalid/v1")


# ── Deepgram (the cloud base + sibling pattern) ───────────────────────────────


@pytest.mark.asyncio
async def test_deepgram_http_error_raises(deepgram, audio):
    with _http(status=500, text="boom"), pytest.raises(ProviderFailed):
        await deepgram.transcribe(audio, "en")


@pytest.mark.asyncio
async def test_deepgram_transport_error_raises(deepgram, audio):
    with _transport_error(), pytest.raises(ProviderFailed):
        await deepgram.transcribe(audio, "en")


@pytest.mark.asyncio
async def test_deepgram_successful_response_without_words_is_silence(deepgram, audio):
    body = {"results": {"channels": [{"alternatives": [{"words": []}]}]}}
    with _http(body=body):
        assert await deepgram.transcribe(audio, "en") == []


# ── AssemblyAI ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assemblyai_upload_error_raises(assemblyai, audio):
    with _http(status=401), pytest.raises(ProviderFailed):
        await assemblyai.transcribe(audio, "en")


@pytest.mark.asyncio
async def test_assemblyai_job_error_raises_and_completed_without_utterances_is_silence(assemblyai, audio):
    with (
        patch.object(assemblyai, "_upload", AsyncMock(return_value="u")),
        patch.object(assemblyai, "_submit", AsyncMock(return_value="t")),
    ):
        with _http(body={"status": "error", "error": "bad"}), pytest.raises(ProviderFailed):
            await assemblyai.transcribe(audio, "en")
        with _http(body={"status": "completed", "utterances": []}):
            assert await assemblyai.transcribe(audio, "en") == []


# ── Google ────────────────────────────────────────────────────────────────────


@pytest.fixture
def google(audio, monkeypatch):
    import voice_processing.providers.cloud.google_provider as gmod

    monkeypatch.setattr(gmod, "_google_available", True)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", audio)
    return GoogleSpeechProvider()


@pytest.mark.asyncio
async def test_google_call_error_raises_and_empty_results_are_silence(google, audio):
    with patch.object(google, "_sync_transcribe", side_effect=RuntimeError("quota")):
        with pytest.raises(ProviderFailed):
            await google.transcribe(audio, "en")
    assert google._parse(MagicMock(results=[]), "en") == []


# ── Tilde ─────────────────────────────────────────────────────────────────────


def test_tilde_without_a_key_is_unavailable(audio):
    provider = TildeProvider(api_key="", api_url="https://asr.invalid/v1")
    provider.api_key = None
    assert provider.is_available() is False


@pytest.mark.asyncio
async def test_tilde_without_a_key_raises_unavailable(audio):
    provider = TildeProvider(api_key="", api_url="https://asr.invalid/v1")
    provider.api_key = None
    with pytest.raises(ProviderUnavailable):
        await provider.transcribe(audio, "lv")


@pytest.mark.asyncio
async def test_tilde_http_error_transport_error_and_timeout_raise(tilde, audio):
    with _http(status=503, text="x"), pytest.raises(ProviderFailed):
        await tilde.transcribe(audio, "lv")
    with _transport_error(), pytest.raises(ProviderFailed):
        await tilde.transcribe(audio, "lv")
    with patch.object(get_http_client(), "tracked_request", side_effect=asyncio.TimeoutError()):
        with pytest.raises(ProviderFailed):
            await tilde.transcribe(audio, "lv")


@pytest.mark.asyncio
async def test_tilde_success_with_no_segments_is_silence(tilde, audio):
    with _http(body={"transcription": {"segments": []}}):
        assert await tilde.transcribe(audio, "lv") == []


# ── LATE ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def late_present():
    done = subprocess.CompletedProcess([], 0, stdout="late 1.0", stderr="")
    with patch("voice_processing.providers.lv.late_provider.subprocess.run", return_value=done):
        yield LateProvider(late_binary_path="late")


def test_late_with_a_missing_binary_is_unavailable():
    provider = LateProvider(late_binary_path="/nonexistent/late-binary")
    assert provider.is_available() is False


@pytest.mark.asyncio
async def test_late_with_a_missing_binary_raises_unavailable(audio):
    with pytest.raises(ProviderUnavailable):
        await LateProvider(late_binary_path="/nonexistent/late-binary").transcribe(audio, "lv")


@pytest.mark.asyncio
async def test_late_nonzero_exit_timeout_and_bad_json_raise(late_present, audio):
    path = "voice_processing.providers.lv.late_provider.subprocess.run"
    failed = subprocess.CompletedProcess([], 2, stdout="", stderr="err")
    with patch(path, return_value=failed), pytest.raises(ProviderFailed):
        await late_present.transcribe(audio, "lv")
    with patch(path, side_effect=subprocess.TimeoutExpired("late", 300)), pytest.raises(ProviderFailed):
        await late_present.transcribe(audio, "lv")
    garbage = subprocess.CompletedProcess([], 0, stdout="not json", stderr="")
    with patch(path, return_value=garbage), pytest.raises(ProviderFailed):
        await late_present.transcribe(audio, "lv")


@pytest.mark.asyncio
async def test_late_valid_output_without_segments_is_silence(late_present, audio):
    ok = subprocess.CompletedProcess([], 0, stdout='{"segments": []}', stderr="")
    with patch("voice_processing.providers.lv.late_provider.subprocess.run", return_value=ok):
        assert await late_present.transcribe(audio, "lv") == []


# ── Generic ───────────────────────────────────────────────────────────────────


def _recognition(text):
    return MagicMock(
        spec=SpeechRecognitionResult, transcription=text, speech_segments=[], confidence=0.9, language="en"
    )


@pytest.fixture
def generic(tmp_path):
    import io
    import wave

    path = tmp_path / "g.wav"
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    path.write_bytes(buf.getvalue())
    return GenericProvider(), str(path)


@pytest.mark.asyncio
async def test_generic_engine_failure_raises_and_an_empty_transcription_is_silence(generic):
    provider, path = generic
    with patch.object(provider.engine, "transcribe_audio", AsyncMock(side_effect=RuntimeError("engine"))):
        with pytest.raises(ProviderFailed):
            await provider.transcribe(path, "en")
    with patch.object(provider.engine, "transcribe_audio", AsyncMock(return_value=_recognition(""))):
        assert await provider.transcribe(path, "en") == []


@pytest.mark.asyncio
async def test_generic_unreadable_wav_raises_not_silence(generic, audio):
    provider, _ = generic
    with pytest.raises(ProviderFailed):  # `audio` is 64 zero bytes: not a WAV
        await provider.transcribe(audio, "en")


# ── the chain, end to end, with the real classes ─────────────────────────────


def _latvian_chain(late, tilde, generic):
    registry = ProviderRegistry()
    registry.register("lv", late, priority=10)
    registry.register("lv", tilde, priority=5)
    registry.register("lv", generic, priority=-10)
    registry.declare_primary_external("lv", tilde)
    return registry


@pytest.mark.asyncio
async def test_latvian_without_the_late_binary_reaches_tilde(tilde, audio):
    registry = _latvian_chain(LateProvider(late_binary_path="/nonexistent/late-binary"), tilde, GenericProvider())
    body = {"transcription": {"segments": [{"text": "sveiki", "start": 0.0, "end": 1.0, "confidence": 0.9}]}}
    with _http(body=body):
        outcome = await registry.transcribe_with_fallback(audio, "lv")
    assert outcome.provider is tilde
    assert [s.text for s in outcome.segments] == ["sveiki"]


@pytest.mark.asyncio
async def test_latvian_without_late_and_with_tilde_failing_is_a_failure_not_empty_and_skips_generic(tilde, audio):
    generic = GenericProvider()
    registry = _latvian_chain(LateProvider(late_binary_path="/nonexistent/late-binary"), tilde, generic)
    with patch.object(generic.engine, "transcribe_audio", AsyncMock()) as run, _http(status=500, text="x"):
        with pytest.raises(TranscriptionUnavailableError) as caught:
            await registry.transcribe_with_fallback(audio, "lv")
    run.assert_not_called()
    assert "LATE: unavailable" in caught.value.reasons
    assert "Tilde: ProviderFailed" in caught.value.reasons


@pytest.mark.asyncio
async def test_a_failed_selected_cloud_is_a_failure_and_never_reaches_a_second_cloud(deepgram, assemblyai, audio):
    registry = ProviderRegistry()
    registry.register("en", deepgram, priority=20)
    registry.register("en", assemblyai, priority=15)
    with patch.object(assemblyai, "_upload", AsyncMock()) as upload, _http(status=500, text="x"):
        with pytest.raises(TranscriptionUnavailableError):
            await registry.transcribe_with_fallback(audio, "en")
    upload.assert_not_called()
