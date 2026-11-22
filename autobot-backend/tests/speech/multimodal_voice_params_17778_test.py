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

from unittest.mock import MagicMock, create_autospec, patch

import numpy as np
import pytest

import multimodal_processor.processors.voice as voice_module
from multimodal_processor.models import MultiModalInput
from multimodal_processor.types import ModalityType, MultimodalProcessingIntent


class _WhisperPipe:
    """The HF ASR pipeline's call signature, as ``transcribe_array`` uses it."""

    def __call__(self, inputs, *, return_timestamps, generate_kwargs):
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
    """The processor with the ONE pinned Whisper pipeline replaced by an autospec'd fake (#17778)."""
    pipe = create_autospec(_WhisperPipe, instance=True, spec_set=True)
    pipe.return_value = {"text": "  hello  "}
    with patch.object(voice_module, "get_whisper_pipeline", return_value=pipe):
        yield processor, pipe


def _audio_input(data) -> MultiModalInput:
    return MultiModalInput(
        input_id="t", modality_type=ModalityType.AUDIO, intent=MultimodalProcessingIntent.VOICE_COMMAND, data=data
    )


def _no_cuda_torch():
    torch = MagicMock()
    torch.cuda.is_available.return_value = False
    return torch


def test_whisper_is_fed_the_given_rate_and_float32_and_generate_keywords(wired) -> None:
    """Adapted to the pipeline seam (#17778): the asserted VALUES are unchanged -- rate,
    float32 samples, and max_length=448 / num_beams=5 / temperature=0.8."""
    processor, pipe = wired
    audio = np.zeros(1600, dtype=np.float32)
    text = processor._transcribe_with_whisper(audio, 16000)
    assert text == "hello"
    (inputs,), kwargs = pipe.call_args
    assert inputs["sampling_rate"] == 16000
    assert inputs["raw"].dtype == np.float32
    assert kwargs["generate_kwargs"] == {"max_length": 448, "num_beams": 5, "temperature": 0.8}


def test_no_pipeline_is_an_error_not_empty_text(processor) -> None:
    """A pipeline that cannot load must surface as a failed result, not as silence."""
    with patch.object(voice_module, "get_whisper_pipeline", return_value=None):
        with pytest.raises(RuntimeError, match="unavailable"):
            processor._transcribe_with_whisper(np.zeros(4, dtype=np.float32), 16000)


def test_container_bytes_are_decoded_not_read_as_float32(processor) -> None:
    """DELIBERATELY CHANGED PIN (#17778, user-visible fix).

    This used to assert that upload bytes were reinterpreted as float32 at 16 kHz.
    That was the defect: the upload route passes a WAV/webm FILE's bytes, so the old
    behaviour transcribed the container header as noise. The rate (16000) and dtype
    (float32) pins stand; the content is now the decoded waveform. The full decode
    contract lives in media/audio/decode_17778_test.py.
    """
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(np.array([0, 16384, -16384, 0], dtype="<i2").tobytes())
    audio, rate = processor._prepare_audio_data(_audio_input(buf.getvalue()))
    assert (rate, audio.dtype) == (16000, np.float32)
    np.testing.assert_allclose(audio, [0.0, 0.5, -0.5, 0.0])


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


def test_the_result_reports_the_device_whisper_actually_runs_on(processor) -> None:
    """processing_device is Whisper's device, not the Wav2Vec2 model's (#17778)."""
    with patch.object(voice_module, "whisper_device", return_value="cpu"):
        result = processor._build_voice_result("hi", "hi", "x", np.zeros(16, dtype=np.float32), 16000, None)
    assert result["processing_device"] == "cpu"
    assert "wav2vec_device" in result
