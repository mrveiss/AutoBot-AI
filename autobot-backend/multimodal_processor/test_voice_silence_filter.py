# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The multimodal Whisper path must drop silence hallucinations too (#13104).

``VoiceProcessor`` runs openai/whisper-base directly, so it is the path the
issue is literally about: fed ambient noise the model returns a fluent phrase
that ``_classify_command`` then turns into a voice command.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import multimodal_processor.processors.voice as voice_module
from voice_processing.hallucination_filter import SILENCE_RMS_THRESHOLD

SAMPLES = 16000


@pytest.fixture
def processor():
    with (
        patch.object(voice_module, "_get_torch", return_value=MagicMock()),
        patch.object(voice_module.VoiceProcessor, "_load_models", lambda self: None),
    ):
        return voice_module.VoiceProcessor()


def _audio_at(rms: float) -> np.ndarray:
    """Constant-magnitude waveform with exactly the requested RMS."""
    return np.full(SAMPLES, rms, dtype=np.float32)


class TestWhisperSilenceArtifactsAreDropped:
    def test_phantom_phrase_over_silence_becomes_empty(self, processor):
        silence = _audio_at(SILENCE_RMS_THRESHOLD / 10)

        assert processor._reject_silence_hallucination("Thanks for watching!", silence, SAMPLES) == ""

    def test_digital_silence_drops_any_transcript(self, processor):
        assert (
            processor._reject_silence_hallucination("open the browser", np.zeros(SAMPLES, dtype=np.float32), SAMPLES)
            == ""
        )

    def test_bare_audio_tag_is_dropped_even_with_energy(self, processor):
        assert processor._reject_silence_hallucination("[BLANK_AUDIO]", _audio_at(0.08), SAMPLES) == ""

    def test_dropped_transcript_classifies_as_unknown_not_a_command(self, processor):
        """The point of the filter: no phantom command reaches the agent."""
        dropped = processor._reject_silence_hallucination("Thanks for watching!", _audio_at(0.0), SAMPLES)

        assert processor._classify_command(dropped) == "unknown"


class TestRealSpeechSurvivesTheWhisperPath:
    @pytest.mark.parametrize("transcript", ["okay", "no", "yeah", "bye", "open firefox"])
    def test_real_audio_keeps_the_transcript(self, processor, transcript):
        assert processor._reject_silence_hallucination(transcript, _audio_at(0.08), SAMPLES) == transcript

    def test_empty_transcript_is_returned_unchanged(self, processor):
        assert processor._reject_silence_hallucination("", _audio_at(0.08), SAMPLES) == ""

    def test_empty_audio_array_does_not_raise(self, processor):
        """A zero-length buffer must not blow up the RMS computation."""
        assert processor._reject_silence_hallucination("okay", np.array([], dtype=np.float32), SAMPLES) == ""
