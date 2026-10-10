# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Whisper pipeline tests
# Issue #932: Implement actual audio transcription
# Issue #17778: AudioPipeline was removed; its behavioural tests moved to the seams that survive

"""Unit tests for the one pinned Whisper inference path."""

import os
from unittest.mock import MagicMock

from media.audio.pipeline import suffix_for_mime, transcribe_array, transcribe_bytes


class TestSuffixMapping:
    def test_known_mimes(self):
        assert suffix_for_mime("audio/mpeg") == ".mp3"
        assert suffix_for_mime("audio/wav") == ".wav"
        assert suffix_for_mime("audio/ogg") == ".ogg"
        assert suffix_for_mime("audio/flac") == ".flac"
        assert suffix_for_mime("audio/webm") == ".webm"

    def test_unknown_mime_defaults_to_wav(self):
        assert suffix_for_mime("audio/unknown") == ".wav"
        assert suffix_for_mime("") == ".wav"


class TestTranscribeBytes:
    def test_writes_temp_file_and_cleans_up(self):
        """Asserts the temp file is GONE, not that `os.unlink` was called once (#17780)."""
        seen_paths = []

        def capture(path, **kwargs):
            seen_paths.append(path)
            return {"text": " hello world ", "language": "en", "chunks": []}

        result = transcribe_bytes(MagicMock(side_effect=capture), b"fake audio bytes", mime="audio/wav")

        assert result.text == "hello world"
        assert result.language == "en"
        assert len(seen_paths) == 1, "Whisper was handed something other than exactly one temp path"
        assert seen_paths[0].endswith(".wav"), f"temp file got the wrong suffix: {seen_paths[0]}"
        assert not os.path.exists(seen_paths[0]), f"temp file was left behind: {seen_paths[0]}"

    def test_non_dict_output_is_empty_unknown(self):
        result = transcribe_bytes(MagicMock(return_value="not a dict"), b"bytes", mime="audio/wav")
        assert result.text == ""
        assert result.language == "unknown"

    def test_language_hint_is_passed_only_when_set(self):
        pipe = MagicMock(return_value={"text": "x"})
        transcribe_bytes(pipe, b"b", language="lv")
        assert pipe.call_args.kwargs["generate_kwargs"] == {"language": "lv"}
        transcribe_bytes(pipe, b"b")
        assert pipe.call_args.kwargs["generate_kwargs"] is None


class TestTranscribeArray:
    def test_passes_raw_array_rate_and_generate_kwargs_untouched(self):
        pipe = MagicMock(return_value={"text": " hi ", "language": "en"})
        samples = [0.0, 0.1]
        kwargs = {"max_length": 448, "num_beams": 5, "temperature": 0.8}
        result = transcribe_array(pipe, samples, 16000, generate_kwargs=kwargs)
        assert result.text == "hi"
        (inputs,), call_kwargs = pipe.call_args
        assert inputs == {"raw": samples, "sampling_rate": 16000}
        assert call_kwargs["generate_kwargs"] == kwargs

    def test_non_dict_output_is_empty(self):
        assert transcribe_array(MagicMock(return_value=None), [0.0], 16000).text == ""
