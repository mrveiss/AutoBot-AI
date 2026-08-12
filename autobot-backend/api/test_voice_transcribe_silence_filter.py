# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The live /api/voice/transcribe route must not emit phantom turns (#13104).

This is the route the issue is actually about. `useVoiceConversation.ts` — the
composable that runs walkie-talkie, hands-free and full-duplex modes — POSTs
recorded audio here, so an unfiltered Whisper hallucination on this path is
exactly the "phantom user turn" #13104 describes.

The transformers ASR pipeline returns neither a language nor a no-speech
probability, so these tests also pin the fallback behaviour: the caller's
requested language keys the denylist, and the gates that need audio signals
fail open rather than guessing.
"""

from unittest.mock import MagicMock

import pytest

from api.voice import _whisper_sync


def _pipe(text: str, language: str | None = None):
    """Stand-in for the transformers ASR pipeline callable."""
    output = {"text": text}
    if language is not None:
        output["language"] = language
    return MagicMock(return_value=output)


class TestHallucinationsAreDiscardedOnTheLiveRoute:
    def test_structural_artifact_is_discarded(self):
        result = _whisper_sync(_pipe("Subtitles by the Amara.org community"), b"x", ".wav", "en")

        assert result["text"] == ""
        assert result["confidence"] == 0.0

    def test_outro_artifact_is_discarded_when_no_energy_is_available(self):
        """The pipeline gives no RMS, which is the hands-free hallucination case."""
        result = _whisper_sync(_pipe("Thanks for watching!"), b"x", ".wav", "en")

        assert result["text"] == ""
        assert result["confidence"] == 0.0

    def test_bare_audio_tag_is_discarded_without_any_language(self):
        result = _whisper_sync(_pipe("[BLANK_AUDIO]"), b"x", ".wav", "")

        assert result["text"] == ""

    def test_requested_language_keys_the_denylist(self):
        """The pipeline reports no language, so the form's value must be used.

        Without this fallback the language is "unknown", the denylist is
        disabled by design, and the filter would be dead on the live route.
        """
        assert _whisper_sync(_pipe("Paldies par skatīšanos!"), b"x", ".wav", "lv")["text"] == ""
        # Same phrase, wrong language key — not an artifact in English.
        assert _whisper_sync(_pipe("Paldies par skatīšanos!"), b"x", ".wav", "en")["text"] != ""

    def test_detected_language_wins_over_the_requested_one(self):
        result = _whisper_sync(_pipe("Thanks for watching!", language="en"), b"x", ".wav", "lv")

        assert result["text"] == ""

    def test_discard_is_logged_with_the_text(self, caplog):
        """Owner rule: no silent dropping — a swallowed turn must be diagnosable."""
        with caplog.at_level("INFO"):
            _whisper_sync(_pipe("Subtitles by the Amara.org community"), b"x", ".wav", "en")

        assert "Subtitles by the Amara.org community" in caplog.text


class TestRealSpeechStillTranscribes:
    @pytest.mark.parametrize("transcript", ["okay", "no", "yeah", "bye", "yes", "open the browser"])
    def test_real_answer_survives(self, transcript):
        result = _whisper_sync(_pipe(transcript), b"x", ".wav", "en")

        assert result["text"] == transcript
        assert result["confidence"] == 0.9

    def test_unknown_language_disables_the_denylist_but_not_the_route(self):
        result = _whisper_sync(_pipe("Thanks for watching!"), b"x", ".wav", "")

        assert result["text"] == "Thanks for watching!"

    def test_empty_transcript_is_unchanged(self):
        result = _whisper_sync(_pipe(""), b"x", ".wav", "en")

        assert result["text"] == ""
        assert result["confidence"] == 0.0

    def test_pipeline_failure_still_returns_the_empty_shape(self):
        failing = MagicMock(side_effect=RuntimeError("model exploded"))

        result = _whisper_sync(failing, b"x", ".wav", "en")

        assert result == {"text": "", "language": "unknown", "confidence": 0.0}
