# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The silence filter must actually be wired into the STT path (#13104).

A correct filter module that nothing calls fixes nothing, so these tests drive
``SpeechRecognitionEngine`` itself: a hallucinated transcript over silent audio
must come back blank, and a real short answer over real audio must come back
intact.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from voice_processing.hallucination_filter import SILENCE_RMS_THRESHOLD
from voice_processing.models import AudioInput
from voice_processing.speech_recognition import SpeechRecognitionEngine

SPEECH_RMS = 0.08
SILENT_RMS = SILENCE_RMS_THRESHOLD / 10
SAMPLE_RATE = 16000


def _audio(rms: float, seconds: float = 1.0) -> AudioInput:
    """AudioInput whose waveform has exactly the requested RMS."""
    samples = np.full(int(SAMPLE_RATE * seconds), rms, dtype=np.float32)
    return AudioInput(
        audio_id="test-audio",
        audio_data=samples,
        sample_rate=SAMPLE_RATE,
        duration=seconds,
        format="raw",
        channels=1,
        timestamp=0.0,
        metadata={},
    )


@pytest.fixture
def engine():
    """Engine with a stand-in recognizer, so the filter is not bypassed."""
    instance = SpeechRecognitionEngine.__new__(SpeechRecognitionEngine)
    instance.recognizer = MagicMock()
    instance.language_detector = None
    instance.noise_reducer = None
    return instance


def _result(transcription: str, language: str = "en") -> dict:
    return {
        "transcription": transcription,
        "confidence": 0.97,
        "alternatives": [],
        "language": language,
    }


class TestSilenceArtifactsAreDiscarded:
    def test_artifact_over_silence_yields_no_transcript(self, engine):
        filtered = engine._discard_silence_artifacts(_result("Thanks for watching!"), _audio(SILENT_RMS))

        assert filtered["transcription"] == ""
        assert filtered["confidence"] == 0.0
        assert filtered["silence_artifact_discarded"] is True

    def test_structural_artifact_with_normal_energy_still_discarded(self, engine):
        filtered = engine._discard_silence_artifacts(
            _result("Subtitles by the Amara.org community"), _audio(SPEECH_RMS)
        )

        assert filtered["transcription"] == ""

    def test_confident_sentence_over_silence_is_discarded(self, engine):
        """High STT confidence is exactly how this failure presents."""
        filtered = engine._discard_silence_artifacts(_result("open the browser"), _audio(SILENT_RMS))

        assert filtered["transcription"] == ""


class TestRealSpeechIsUntouched:
    @pytest.mark.parametrize("transcript", ["okay", "no", "yeah", "bye", "yes", "stop"])
    def test_short_real_answer_still_registers_as_a_turn(self, engine, transcript):
        original = _result(transcript)
        filtered = engine._discard_silence_artifacts(original, _audio(SPEECH_RMS))

        assert filtered["transcription"] == transcript
        assert filtered is original
        assert "silence_artifact_discarded" not in filtered

    def test_sentence_is_passed_through_unchanged(self, engine):
        original = _result("open the browser and search for trains")
        assert engine._discard_silence_artifacts(original, _audio(SPEECH_RMS)) is original

    def test_unknown_language_disables_the_denylist(self, engine):
        original = _result("Thanks for watching!", language="unknown")
        assert engine._discard_silence_artifacts(original, _audio(SPEECH_RMS)) is original

    def test_placeholder_transcript_survives_when_no_recognizer(self, engine):
        """Without a recognizer the transcript is diagnostic text, not a turn."""
        engine.recognizer = None
        original = _result("[Speech recognition not available]")

        assert engine._discard_silence_artifacts(original, _audio(SILENT_RMS)) is original


class TestNoiseLevelIsNotReusedAsSpeechEnergy:
    """Review item C: the gate must not depend on _calculate_noise_level."""

    def test_gate_reads_the_waveform_not_the_noise_level_helper(self, engine, monkeypatch):
        """If _calculate_noise_level were the source, this would invert."""
        monkeypatch.setattr(
            SpeechRecognitionEngine,
            "_calculate_noise_level",
            lambda self, audio_input: 0.0,  # a "quiet room" reading
        )
        original = _result("open the browser")

        assert engine._discard_silence_artifacts(original, _audio(SPEECH_RMS)) is original

    def test_short_utterance_in_a_long_buffer_survives(self, engine):
        """Review item D end-to-end: 0.5s of speech inside 30s of silence."""
        samples = np.zeros(SAMPLE_RATE * 30, dtype=np.float32)
        samples[: int(SAMPLE_RATE * 0.5)] = 0.03
        audio = AudioInput(
            audio_id="short-utterance",
            audio_data=samples,
            sample_rate=SAMPLE_RATE,
            duration=30.0,
            format="raw",
            channels=1,
            timestamp=0.0,
            metadata={},
        )
        original = _result("okay")

        assert engine._discard_silence_artifacts(original, audio) is original

    def test_bytes_audio_disables_the_energy_gate_rather_than_guessing(self, engine):
        audio = AudioInput(
            audio_id="raw-bytes",
            audio_data=b"\x00\x01",
            sample_rate=SAMPLE_RATE,
            duration=1.0,
            format="wav",
            channels=1,
            timestamp=0.0,
            metadata={},
        )
        original = _result("open the browser")

        assert engine._discard_silence_artifacts(original, audio) is original
