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
from unittest.mock import MagicMock, patch

from media.audio.pipeline import (
    suffix_for_mime,
    transcribe_array,
    transcribe_bytes,
    whisper_device,
    whisper_device_kwargs,
)


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


class TestWhisperDevice:
    """AUTOBOT_WHISPER_DEVICE (#17778): cpu is byte-identical to the historical call."""

    def _torch(self, monkeypatch, cuda):
        import sys
        import types

        fake = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: cuda), float16="FP16")
        monkeypatch.setitem(sys.modules, "torch", fake)

    def test_default_is_auto_cuda_fp16_when_available(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_WHISPER_DEVICE", raising=False)
        self._torch(monkeypatch, cuda=True)
        assert whisper_device_kwargs() == {"device": "cuda", "torch_dtype": "FP16"}

    def test_default_without_cuda_adds_no_device_or_dtype_kwargs(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_WHISPER_DEVICE", raising=False)
        self._torch(monkeypatch, cuda=False)
        assert whisper_device_kwargs() == {}

    def test_cpu_forces_the_historical_call_even_with_cuda(self, monkeypatch):
        monkeypatch.setenv("AUTOBOT_WHISPER_DEVICE", "cpu")
        self._torch(monkeypatch, cuda=True)
        assert whisper_device_kwargs() == {}

    def test_default_hf_pipeline_call_without_cuda_is_exactly_the_historical_one(self, monkeypatch):
        import media.audio.pipeline as module

        monkeypatch.delenv("AUTOBOT_WHISPER_DEVICE", raising=False)
        self._torch(monkeypatch, cuda=False)
        hf = MagicMock(return_value="PIPE")
        monkeypatch.setattr(module, "hf_pipeline", hf, raising=False)
        monkeypatch.setattr(module, "_TRANSFORMERS_AVAILABLE", True)
        monkeypatch.setattr(module, "_whisper_pipeline", None)
        monkeypatch.setattr(module, "_whisper_retry_at", 0.0)
        monkeypatch.setattr("autobot_shared.pinned_model_registry.load_verified", lambda repo, loader: (loader("REV"),))
        assert module.get_whisper_pipeline() == "PIPE"
        hf.assert_called_once_with("automatic-speech-recognition", model="openai/whisper-base", revision="REV")

    def test_auto_with_cuda_is_cuda_fp16(self, monkeypatch):
        monkeypatch.setenv("AUTOBOT_WHISPER_DEVICE", "auto")
        self._torch(monkeypatch, cuda=True)
        assert whisper_device_kwargs() == {"device": "cuda", "torch_dtype": "FP16"}

    def test_auto_without_cuda_is_cpu(self, monkeypatch):
        monkeypatch.setenv("AUTOBOT_WHISPER_DEVICE", "auto")
        self._torch(monkeypatch, cuda=False)
        assert whisper_device_kwargs() == {}

    def test_garbage_is_cpu_with_a_warning(self, monkeypatch):
        import media.audio.pipeline as module

        monkeypatch.setenv("AUTOBOT_WHISPER_DEVICE", "tpu")
        with patch.object(module.logger, "warning") as warn:
            assert whisper_device_kwargs() == {}
        assert warn.called

    def test_reported_device_is_the_loaded_pipelines(self, monkeypatch):
        import media.audio.pipeline as module

        monkeypatch.setattr(module, "_whisper_pipeline", MagicMock(device="cuda:0"))
        assert whisper_device() == "cuda:0"
