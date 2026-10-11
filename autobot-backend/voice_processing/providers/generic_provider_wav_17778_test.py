# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GenericProvider builds a complete AudioInput from a real WAV (#17778).

Before the fix both ``AudioInput(...)`` constructions omitted the required
``format``, ``channels`` and ``timestamp`` fields, so every call raised
``TypeError`` -- caught by ``transcribe`` and reported as ``[]``. The recognizer
here is a fake and ``urlopen`` is poisoned: this test performs no egress.
"""

import math
import struct
import wave
from unittest.mock import create_autospec, patch

import pytest

from voice_processing.models import AudioInput, SpeechRecognitionResult
from voice_processing.providers.generic_provider import GenericProvider
from voice_processing.speech_recognition import SpeechRecognitionEngine
from voice_processing.types import SpeechQuality

RATE, CHANNELS, SECONDS = 22_050, 2, 0.5


def _write_wav(path) -> int:
    frames = int(RATE * SECONDS)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        for i in range(frames):
            sample = int(12_000 * math.sin(2 * math.pi * 440 * i / RATE))
            wav.writeframes(struct.pack("<hh", sample, sample))
    return frames


def _result() -> SpeechRecognitionResult:
    return SpeechRecognitionResult(
        audio_id="t.wav",
        transcription="hello",
        confidence=0.8,
        language="en",
        alternative_transcriptions=[],
        speech_segments=[],
        audio_quality=SpeechQuality.GOOD,
        noise_level=0.0,
        processing_time=0.0,
        metadata={},
    )


@pytest.fixture
def provider():
    gen = GenericProvider()
    gen.engine = create_autospec(SpeechRecognitionEngine, instance=True)
    gen.engine.recognizer = object()  # an instance attribute set in __init__, so not on the spec
    gen.engine.transcribe_audio.return_value = _result()
    return gen


@pytest.mark.asyncio
async def test_transcribe_returns_segments_for_a_real_wav_without_egress(provider, tmp_path):
    wav_path = tmp_path / "t.wav"
    _write_wav(wav_path)
    with patch("urllib.request.urlopen", side_effect=AssertionError("network egress attempted")):
        segments = await provider.transcribe(str(wav_path), "en")
    assert len(segments) == 1, "transcribe swallowed an AudioInput construction error and returned []"
    provider.engine.transcribe_audio.assert_awaited_once()


@pytest.mark.asyncio
async def test_audio_input_carries_the_wav_header_values(provider, tmp_path):
    wav_path = tmp_path / "t.wav"
    frames = _write_wav(wav_path)
    audio = await provider._load_audio_input(str(wav_path))
    assert isinstance(audio, AudioInput)
    assert (audio.sample_rate, audio.channels, audio.format) == (RATE, CHANNELS, "wav")
    assert audio.duration == pytest.approx(frames / RATE)
    assert audio.timestamp > 0
    assert audio.metadata["sample_width"] == 2
    assert "load_error" not in audio.metadata


@pytest.fixture
def bad_wav(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wav")
    return bad


@pytest.mark.asyncio
async def test_unreadable_file_still_yields_a_complete_AudioInput(provider, bad_wav):
    bad = bad_wav
    audio = await provider._load_audio_input(str(bad))
    assert audio.audio_data == b"" and "load_error" in audio.metadata
    assert audio.format and audio.channels >= 1 and audio.timestamp > 0
