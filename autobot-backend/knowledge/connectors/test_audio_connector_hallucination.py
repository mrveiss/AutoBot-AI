# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whisper hallucinations must not be ingested into the knowledge base (#13104).

openai-whisper is the one STT backend in the tree that reports
``no_speech_prob`` per segment, so this is where that gate — and the
``AUTOBOT_STT_NO_SPEECH_PROB_THRESHOLD`` knob — actually has a producer.
Ingesting a phantom sentence would put text in the KB that no source ever
contained, and unlike a phantom voice turn it persists.
"""

import pytest

from knowledge.connectors.audio_connector import _mean_no_speech_prob, _reject_hallucinated_transcript
from voice_processing.hallucination_filter import NO_SPEECH_PROB_THRESHOLD


def _result(text: str, no_speech_probs=None, language=None) -> dict:
    result: dict = {"text": text}
    if language is not None:
        result["language"] = language
    if no_speech_probs is not None:
        result["segments"] = [{"no_speech_prob": p} for p in no_speech_probs]
    return result


class TestNoSpeechProbabilityGate:
    def test_high_no_speech_probability_discards_the_transcript(self):
        result = _result("Thanks for watching!", [0.97, 0.95], language="en")

        assert _reject_hallucinated_transcript(result, "en") == ""

    def test_high_probability_discards_even_plausible_text(self):
        """The decoder is saying there was no speech at all."""
        result = _result("the quarterly figures were strong", [0.99], language="en")

        assert _reject_hallucinated_transcript(result, "en") == ""

    def test_low_no_speech_probability_keeps_the_transcript(self):
        result = _result("the quarterly figures were strong", [0.01, 0.02], language="en")

        assert _reject_hallucinated_transcript(result, "en") == "the quarterly figures were strong"

    def test_probability_is_averaged_across_segments(self):
        probs = [0.0, 1.0]
        assert _mean_no_speech_prob(_result("x", probs)) == pytest.approx(0.5)
        assert 0.5 < NO_SPEECH_PROB_THRESHOLD
        assert _reject_hallucinated_transcript(_result("real speech here", probs), "en") == "real speech here"

    def test_missing_segments_yield_none_not_zero(self):
        """None means 'no evidence'; 0.0 would falsely mean 'definitely speech'."""
        assert _mean_no_speech_prob({"text": "x"}) is None
        assert _mean_no_speech_prob({"text": "x", "segments": []}) is None

    def test_backend_without_the_field_falls_back_to_phrase_gates(self):
        assert _reject_hallucinated_transcript(_result("Subtitles by the Amara.org community"), "en") == ""
        assert _reject_hallucinated_transcript(_result("a normal sentence"), "en") == "a normal sentence"


class TestLanguageResolution:
    def test_detected_language_is_preferred(self):
        result = _result("Paldies par skatīšanos!", language="lv")

        assert _reject_hallucinated_transcript(result, "en") == ""

    def test_requested_language_is_the_fallback(self):
        assert _reject_hallucinated_transcript(_result("Paldies par skatīšanos!"), "lv") == ""

    def test_no_language_disables_the_phrase_gates(self):
        assert _reject_hallucinated_transcript(_result("Thanks for watching!"), None) == "Thanks for watching!"


class TestDiscardIsDiagnosable:
    def test_discarded_ingestion_is_logged_with_the_text(self, caplog):
        with caplog.at_level("INFO"):
            _reject_hallucinated_transcript(_result("Thanks for watching!", [0.99]), "en")

        assert "Thanks for watching!" in caplog.text
