# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Characterization of the multimodal VoiceProcessor's audio parameters (#17778).

``multimodal_processor/processors/voice.py`` is the second in-process copy of
``openai/whisper-base``. A consolidation slice will route it through the shared
pipeline, so what it feeds the model today is pinned here: the sampling rate,
the input dtype, the mono reduction, and the ``generate`` keywords.

Fakes are ``create_autospec`` of classes carrying the signatures the code calls,
so a renamed keyword reddens the test instead of being swallowed by a MagicMock.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, create_autospec, patch

import numpy as np
import pytest

import multimodal_processor.processors.voice as voice_module
from multimodal_processor.models import MultiModalInput
from multimodal_processor.types import ModalityType, ProcessingIntent


class _WhisperProcessor:
    def __call__(self, audio, *, sampling_rate, return_tensors):
        raise NotImplementedError

    def batch_decode(self, ids, *, skip_special_tokens):
        raise NotImplementedError


class _WhisperModel:
    def generate(self, input_features, *, max_length, num_beams, temperature):
        raise NotImplementedError


class _Librosa:
    def load(self, path, *, sr):
        raise NotImplementedError


@pytest.fixture
def processor():
    with (
        patch.object(voice_module, "_get_torch", return_value=MagicMock()),
        patch.object(voice_module.VoiceProcessor, "_load_models", lambda self: None),
    ):
        return voice_module.VoiceProcessor()


@pytest.fixture
def wired(processor):
    """The processor with an autospec'd Whisper processor and model attached."""
    asr_processor = create_autospec(_WhisperProcessor, instance=True, spec_set=True)
    asr_processor.return_value = SimpleNamespace(input_features="FEATURES")
    asr_processor.batch_decode.return_value = ["  hello  "]
    model = create_autospec(_WhisperModel, instance=True, spec_set=True)
    model.generate.return_value = "IDS"
    processor.whisper_processor = asr_processor
    processor.whisper_model = model
    return processor, asr_processor, model


def _audio_input(data) -> MultiModalInput:
    return MultiModalInput(
        input_id="t", modality_type=ModalityType.AUDIO, intent=ProcessingIntent.VOICE_COMMAND, data=data
    )


def _no_cuda_torch():
    torch = MagicMock()
    torch.cuda.is_available.return_value = False
    return torch


def test_whisper_is_fed_the_given_rate_and_float32_and_generate_keywords(wired) -> None:
    processor, asr_processor, model = wired
    audio = np.zeros(1600, dtype=np.float32)
    with patch.object(voice_module, "_get_torch", return_value=_no_cuda_torch()):
        text = processor._transcribe_with_whisper(audio, 16000)
    assert text == "hello"
    (seen_audio,), kwargs = asr_processor.call_args
    assert seen_audio.dtype == np.float32
    assert kwargs == {"sampling_rate": 16000, "return_tensors": "pt"}
    model.generate.assert_called_once_with("FEATURES", max_length=448, num_beams=5, temperature=0.8)
    asr_processor.batch_decode.assert_called_once_with("IDS", skip_special_tokens=True)


def test_raw_bytes_are_read_as_float32_at_16khz(processor) -> None:
    samples = np.linspace(-1, 1, 8, dtype=np.float32)
    data = _audio_input(samples.tobytes())
    audio, rate = processor._prepare_audio_data(data)
    assert (rate, audio.dtype) == (16000, np.float32)
    np.testing.assert_array_equal(audio, samples)


def test_a_two_channel_array_is_reduced_to_mono_by_mean(processor) -> None:
    stereo = np.array([[1.0, 3.0], [2.0, 4.0]], dtype=np.float64)
    data = _audio_input(stereo)
    audio, rate = processor._prepare_audio_data(data)
    assert audio.shape == (2,)
    assert audio.dtype == np.float32
    np.testing.assert_array_equal(audio, np.array([2.0, 3.0], dtype=np.float32))
    assert rate == 16000


def test_a_file_path_is_loaded_at_16khz_and_reports_the_loaders_rate(processor, monkeypatch) -> None:
    fake = create_autospec(_Librosa, instance=True, spec_set=True)
    fake.load.return_value = (np.zeros(4, dtype=np.float64), 16000)
    monkeypatch.setattr(voice_module, "librosa", fake, raising=False)
    data = _audio_input("/clip.wav")
    audio, rate = processor._prepare_audio_data(data)
    fake.load.assert_called_once_with("/clip.wav", sr=16000)
    assert (rate, audio.dtype) == (16000, np.float32)
