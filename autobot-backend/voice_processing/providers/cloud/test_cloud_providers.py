# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for cloud ASR provider adapters (Issue #10147).

All HTTP calls are mocked — no live API required.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_processing.providers import TranscriptSegment
from voice_processing.providers.cloud.assemblyai_provider import AssemblyAIProvider
from voice_processing.providers.cloud.deepgram_provider import DeepgramProvider
from voice_processing.providers.cloud.google_provider import GoogleSpeechProvider

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def audio_file(tmp_path):
    """Create a tiny dummy audio file."""
    p = tmp_path / "test.wav"
    p.write_bytes(b"\x00" * 64)
    return str(p)


# ── CloudSpeechProvider base ─────────────────────────────────────────────────


def test_base_is_configured_false_when_no_key():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DEEPGRAM_API_KEY", None)
        p = DeepgramProvider()
    assert not p.is_configured


def test_base_is_configured_true_when_key_set():
    with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "test-key"}):
        p = DeepgramProvider()
    assert p.is_configured


def test_cloud_provider_diarizes_flag():
    with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "k"}):
        p = DeepgramProvider()
    assert p.diarizes is True


# ── Deepgram adapter ─────────────────────────────────────────────────────────


DEEPGRAM_RESPONSE = {
    "results": {
        "channels": [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Hello", "start": 0.1, "end": 0.5, "confidence": 0.98, "speaker": 0},
                            {"word": "world", "start": 0.6, "end": 1.0, "confidence": 0.95, "speaker": 1},
                        ]
                    }
                ]
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_deepgram_transcribe_request_shape(audio_file):
    """Verify Deepgram sends correct params and auth header."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=DEEPGRAM_RESPONSE)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "dg-key-123"}):
        provider = DeepgramProvider()

    with patch("voice_processing.providers.cloud.deepgram_provider.aiohttp.ClientSession", return_value=mock_session):
        segments = await provider.transcribe(audio_file, "en")

    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer dg-key-123"
    assert call_kwargs.kwargs["params"]["diarize"] == "true"

    assert len(segments) == 2
    assert segments[0].speaker == "SPEAKER_00"
    assert segments[1].speaker == "SPEAKER_01"
    assert segments[0].text == "Hello"
    assert segments[0].start_time == pytest.approx(0.1)
    assert segments[0].end_time == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_deepgram_returns_empty_on_api_error(audio_file):
    mock_resp = AsyncMock()
    mock_resp.status = 401
    mock_resp.text = AsyncMock(return_value="unauthorized")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "bad-key"}):
        provider = DeepgramProvider()

    with patch("voice_processing.providers.cloud.deepgram_provider.aiohttp.ClientSession", return_value=mock_session):
        segments = await provider.transcribe(audio_file, "en")

    assert segments == []


@pytest.mark.asyncio
async def test_deepgram_no_key_returns_empty(audio_file):
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DEEPGRAM_API_KEY", None)
        provider = DeepgramProvider()
    segments = await provider.transcribe(audio_file, "en")
    assert segments == []


# ── AssemblyAI adapter ────────────────────────────────────────────────────────


ASSEMBLYAI_COMPLETED = {
    "status": "completed",
    "utterances": [
        {"speaker": "A", "text": "Hello", "start": 0, "end": 500, "confidence": 0.9},
        {"speaker": "B", "text": "Hi", "start": 600, "end": 1000, "confidence": 0.85},
    ],
}


@pytest.mark.asyncio
async def test_assemblyai_transcribe_request_shape(audio_file):
    """Verify upload→submit→poll flow and speaker label mapping."""
    upload_resp = AsyncMock()
    upload_resp.status = 200
    upload_resp.json = AsyncMock(return_value={"upload_url": "https://fake/audio"})
    upload_resp.__aenter__ = AsyncMock(return_value=upload_resp)
    upload_resp.__aexit__ = AsyncMock(return_value=False)

    submit_resp = AsyncMock()
    submit_resp.status = 200
    submit_resp.json = AsyncMock(return_value={"id": "txr123"})
    submit_resp.__aenter__ = AsyncMock(return_value=submit_resp)
    submit_resp.__aexit__ = AsyncMock(return_value=False)

    poll_resp = AsyncMock()
    poll_resp.json = AsyncMock(return_value=ASSEMBLYAI_COMPLETED)
    poll_resp.__aenter__ = AsyncMock(return_value=poll_resp)
    poll_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=[upload_resp, submit_resp])
    mock_session.get = MagicMock(return_value=poll_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "aai-key"}):
        provider = AssemblyAIProvider()

    with patch("voice_processing.providers.cloud.assemblyai_provider.asyncio.sleep", new=AsyncMock()):
        # Each _upload/_submit/_poll creates its own session via _make_session()
        with patch.object(provider, "_make_session", return_value=mock_session):
            segments = await provider.transcribe(audio_file, "en")

    assert len(segments) == 2
    assert segments[0].speaker == "SPEAKER_A"
    assert segments[1].speaker == "SPEAKER_B"
    assert segments[0].start_time == pytest.approx(0.0)
    assert segments[0].end_time == pytest.approx(0.5)
    assert segments[0].text == "Hello"


@pytest.mark.asyncio
async def test_assemblyai_no_key_returns_empty(audio_file):
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ASSEMBLYAI_API_KEY", None)
        provider = AssemblyAIProvider()
    segments = await provider.transcribe(audio_file, "en")
    assert segments == []


# ── Google Cloud STT adapter ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_not_configured_when_lib_absent(audio_file):
    """When google-cloud-speech is not installed, is_configured=False."""
    import voice_processing.providers.cloud.google_provider as gmod

    original = gmod._google_available
    try:
        gmod._google_available = False
        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": audio_file}):
            provider = GoogleSpeechProvider()
        assert not provider.is_configured
        segments = await provider.transcribe(audio_file, "en")
        assert segments == []
    finally:
        gmod._google_available = original


@pytest.mark.asyncio
async def test_google_not_configured_when_no_credentials():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        provider = GoogleSpeechProvider()
    assert not provider.is_configured


@pytest.mark.asyncio
async def test_google_transcribe_uses_diarization_config(audio_file, tmp_path):
    """When lib + credentials present, verify diarization config is passed."""
    creds_file = tmp_path / "creds.json"
    creds_file.write_text("{}", encoding="utf-8")

    mock_word = MagicMock()
    mock_word.word = "Hello"
    mock_word.speaker_tag = 1
    mock_word.start_time.total_seconds.return_value = 0.0
    mock_word.end_time.total_seconds.return_value = 0.5
    mock_word.confidence = 0.95

    mock_alternative = MagicMock()
    mock_alternative.words = [mock_word]

    mock_result = MagicMock()
    mock_result.alternatives = [mock_alternative]

    mock_response = MagicMock()
    mock_response.results = [mock_result]

    mock_client = MagicMock()
    mock_client.recognize.return_value = mock_response

    import voice_processing.providers.cloud.google_provider as gmod

    original = gmod._google_available
    try:
        gmod._google_available = True
        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": str(creds_file)}):
            provider = GoogleSpeechProvider()

        with patch("voice_processing.providers.cloud.google_provider._google_speech") as mock_speech:
            mock_speech.SpeechClient.return_value = mock_client
            mock_speech.RecognitionAudio = MagicMock(return_value=MagicMock())
            mock_speech.SpeakerDiarizationConfig = MagicMock(return_value=MagicMock())
            mock_speech.RecognitionConfig = MagicMock(return_value=MagicMock())
            mock_speech.RecognitionConfig.AudioEncoding = MagicMock()

            segments = await provider.transcribe(audio_file, "en")

        assert len(segments) == 1
        assert segments[0].speaker == "SPEAKER_01"
        assert segments[0].text == "Hello"
        # Verify diarization config was constructed
        mock_speech.SpeakerDiarizationConfig.assert_called_once()
    finally:
        gmod._google_available = original


# ── Provider metadata ─────────────────────────────────────────────────────────


def test_provider_names():
    with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "k"}):
        assert DeepgramProvider().provider_name == "Deepgram"
    with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "k"}):
        assert AssemblyAIProvider().provider_name == "AssemblyAI"
    assert GoogleSpeechProvider().provider_name == "Google Cloud STT"


def test_supported_languages_non_empty():
    with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "k"}):
        assert len(DeepgramProvider().supported_languages) > 0
    with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "k"}):
        assert len(AssemblyAIProvider().supported_languages) > 0
    assert len(GoogleSpeechProvider().supported_languages) > 0
