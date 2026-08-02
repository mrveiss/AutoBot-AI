# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the STT silence-hallucination filter (#13104).

Two obligations pull against each other and both are asserted here:

* silence must never become a user turn, and
* real short answers ("okay", "no", "yeah", "bye") must always survive.

The second set is the important one. A filter that quietly eats one-word
replies makes the assistant look like it is ignoring the user, which is a worse
failure than the phantom turns the filter exists to prevent.
"""

import pytest

from voice_processing.hallucination_filter import (
    SILENCE_RMS_THRESHOLD,
    is_audio_tag,
    is_known_artifact,
    is_silence_hallucination,
    normalize_transcript,
    peak_window_rms,
)

SPEECH_RMS = 0.08  # comfortably above the silence floor
SILENT_RMS = SILENCE_RMS_THRESHOLD / 10


class TestRealShortAnswersSurvive:
    """The hard constraint from #13104: never eat a genuine short reply."""

    @pytest.mark.parametrize(
        "transcript",
        ["okay", "Okay.", "yeah", "no", "No.", "so", "bye", "Bye!", "yes", "stop", "music", "thank you"],
    )
    def test_short_answer_with_real_audio_is_a_turn(self, transcript):
        assert is_silence_hallucination(transcript, "en", rms=SPEECH_RMS) is False

    @pytest.mark.parametrize("language", ["en", "lv", "ru", "de", "es", "fr", None])
    def test_ordinary_sentence_is_a_turn_in_every_language(self, language):
        assert is_silence_hallucination("open the browser and search for trains", language, rms=SPEECH_RMS) is False

    def test_sentence_merely_containing_an_artifact_phrase_survives(self):
        """Matching is exact, not substring — a real sentence must not be eaten."""
        transcript = "before you go, say thanks for watching to the camera"
        assert is_silence_hallucination(transcript, "en", rms=SPEECH_RMS) is False


class TestSilenceIsFiltered:
    """Silence must not produce a turn, whichever signal reveals it."""

    def test_silent_audio_discards_any_transcript(self):
        assert is_silence_hallucination("Thanks for watching!", "en", rms=SILENT_RMS) is True

    def test_silent_audio_discards_a_plausible_sentence_too(self):
        """Below the noise floor there was nothing to transcribe at all."""
        assert is_silence_hallucination("open the browser", "en", rms=SILENT_RMS) is True

    def test_no_speech_probability_discards_transcript(self):
        assert is_silence_hallucination("Thank you.", "en", no_speech_prob=0.95) is True

    def test_low_no_speech_probability_keeps_transcript(self):
        assert is_silence_hallucination("open the browser", "en", no_speech_prob=0.05) is False

    @pytest.mark.parametrize(
        "transcript",
        ["[BLANK_AUDIO]", "(silence)", "[ Music ]", "♪♪", "{inaudible}"],
    )
    def test_bare_audio_tags_are_discarded_without_any_signal(self, transcript):
        assert is_silence_hallucination(transcript) is True
        assert is_audio_tag(transcript) is True


class TestKnownArtifactDenylist:
    """Per-language credit phrases, applied only when the language is known."""

    @pytest.mark.parametrize(
        "language,transcript",
        [
            ("en", "Subtitles by the Amara.org community"),
            ("en", "Transcription by CastingWords"),
            ("lv", "Subtitrus sagatavoja"),
            ("ru", "Субтитры сделал DimaTorzok"),
            ("de", "Untertitelung des ZDF, 2020"),
            ("es", "Subtítulos realizados por la comunidad de Amara.org"),
            ("fr", "Sous-titres réalisés par la communauté d'Amara.org"),
        ],
    )
    def test_structural_artifact_is_discarded_even_with_normal_audio_energy(self, language, transcript):
        """Subtitle credits and URLs are never dictation, whatever the energy."""
        assert is_silence_hallucination(transcript, language, rms=SPEECH_RMS) is True

    @pytest.mark.parametrize(
        "language,transcript",
        [
            ("en", "Thanks for watching!"),
            ("en", "Please subscribe to my channel."),
            ("lv", "Paldies par skatīšanos!"),
            ("ru", "Спасибо за просмотр!"),
            ("de", "Vielen Dank fürs Zuschauen!"),
            ("fr", "Merci d'avoir regardé cette vidéo !"),
        ],
    )
    def test_outro_artifact_is_discarded_when_no_energy_evidence(self, language, transcript):
        """On a live mic with no RMS available, an outro phrase is the artifact."""
        assert is_silence_hallucination(transcript, language) is True

    @pytest.mark.parametrize(
        "language,transcript",
        [
            ("en", "Thanks for watching!"),
            ("en", "Please subscribe to my channel."),
            ("de", "Vielen Dank fürs Zuschauen!"),
        ],
    )
    def test_outro_artifact_survives_when_the_audio_shows_real_speech(self, language, transcript):
        """Review item I: a dictated sign-off with real energy is real speech."""
        assert is_silence_hallucination(transcript, language, rms=SPEECH_RMS) is False

    def test_unknown_language_never_filters(self):
        """Acceptance criterion: no denylist for a locale we have not curated."""
        assert is_silence_hallucination("Subtitles by the Amara.org community", None, rms=SPEECH_RMS) is False
        assert is_silence_hallucination("Subtitles by the Amara.org community", "unknown", rms=SPEECH_RMS) is False
        assert is_silence_hallucination("Subtitles by the Amara.org community", "ja", rms=SPEECH_RMS) is False

    def test_language_region_subtags_resolve_to_the_base_language(self):
        assert is_known_artifact("Thanks for watching!", "en-GB") is True
        assert is_known_artifact("Subtitles by the Amara.org community", "en-GB") is True

    def test_empty_transcript_is_not_a_hallucination(self):
        assert is_silence_hallucination("", "en", rms=SILENT_RMS) is False
        assert is_silence_hallucination("   ", "en", rms=SILENT_RMS) is False


class TestNormalization:
    """Matching is punctuation- and case-insensitive, so table entries stay readable."""

    def test_case_punctuation_and_whitespace_are_folded(self):
        assert normalize_transcript("  Thanks   FOR watching!!  ") == "thanks for watching"

    def test_apostrophes_fold_to_a_space_and_accents_are_kept(self):
        assert normalize_transcript("Merci d'avoir regardé cette vidéo !") == "merci d avoir regardé cette vidéo"

    def test_denylist_entries_are_normalized_at_import(self):
        """Entries written as real sentences still match transcripts."""
        assert is_known_artifact("subtitles by the amara org community", "en") is True
        assert is_known_artifact("Subtitles by the Amara.org community.", "en") is True


class TestMissingSignalsAreNotGuessedAt:
    """Absent signals must never be treated as evidence of silence."""

    def test_no_rms_and_no_probability_leaves_ordinary_speech_alone(self):
        assert is_silence_hallucination("open the browser") is False

    def test_zero_probability_is_not_confused_with_absent(self):
        assert is_silence_hallucination("open the browser", "en", no_speech_prob=0.0) is False

    def test_zero_rms_is_not_confused_with_absent(self):
        assert is_silence_hallucination("open the browser", "en", rms=0.0) is True


class TestPeakWindowRms:
    """Review item D: a short utterance must not average away to silence."""

    def test_short_utterance_in_a_long_silent_buffer_reads_as_speech(self):
        """0.5s of speech in a 30s buffer — whole-buffer RMS would drop this."""
        sample_rate = 16000
        buffer = [0.0] * (30 * sample_rate)
        for i in range(int(0.5 * sample_rate)):
            buffer[i] = 0.03

        whole_buffer_rms = (sum(v * v for v in buffer) / len(buffer)) ** 0.5
        assert whole_buffer_rms < SILENCE_RMS_THRESHOLD, "precondition: the old gate would have dropped this"

        peak = peak_window_rms(buffer, sample_rate)
        assert peak > SILENCE_RMS_THRESHOLD
        assert is_silence_hallucination("okay", "en", rms=peak) is False

    def test_genuinely_silent_buffer_still_reads_as_silence(self):
        sample_rate = 16000
        assert peak_window_rms([0.0] * sample_rate, sample_rate) == 0.0
        assert is_silence_hallucination("Thanks for watching!", "en", rms=0.0) is True

    def test_empty_buffer_is_zero_not_an_error(self):
        assert peak_window_rms([], 16000) == 0.0

    def test_constant_tone_matches_its_own_rms(self):
        assert peak_window_rms([0.5] * 16000, 16000) == pytest.approx(0.5)


class TestDiscardsAreLogged:
    """Owner rule: nothing is dropped silently — every gate must be diagnosable."""

    def test_discard_logs_at_info_with_the_text_and_reason(self, caplog):
        with caplog.at_level("INFO", logger="voice_processing.hallucination_filter"):
            assert is_silence_hallucination("Thanks for watching!", "en", rms=0.0) is True

        assert "Thanks for watching!" in caplog.text
        assert "silence floor" in caplog.text

    def test_kept_transcript_logs_nothing(self, caplog):
        with caplog.at_level("INFO", logger="voice_processing.hallucination_filter"):
            assert is_silence_hallucination("open the browser", "en", rms=SPEECH_RMS) is False

        assert caplog.text == ""

    def test_each_gate_names_itself(self, caplog):
        with caplog.at_level("INFO", logger="voice_processing.hallucination_filter"):
            is_silence_hallucination("anything", "en", no_speech_prob=0.99)
            is_silence_hallucination("[BLANK_AUDIO]", "en")
            is_silence_hallucination("Subtitles by the Amara.org community", "en", rms=SPEECH_RMS)

        assert "no_speech_prob" in caplog.text
        assert "bare audio tag" in caplog.text
        assert "subtitle-credit artifact" in caplog.text
