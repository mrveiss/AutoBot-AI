# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Long audio, failure contract, event-loop safety and loader retry (#17778 review)."""

import math
import struct
import wave
from unittest.mock import MagicMock, create_autospec, patch

import pytest

import media.audio.pipeline as audio_pipeline
from autobot_shared.pinned_model_registry import ModelIntegrityError
from voice_processing.providers import (
    SpeechProvider,
    SpeechProviderRegistry,
    TranscriptionUnavailableError,
    TranscriptSegment,
)
from voice_processing.providers import logger as registry_logger
from voice_processing.providers.whisper_provider import WhisperProvider

LONG_FORM_ERROR = "You have passed more than 3000 mel input features (> 30 seconds) ..."


class LongFormEnforcingPipe:
    """Raises the same ValueError transformers does for > 30 s without timestamps."""

    def __init__(self):
        self.calls = []

    @staticmethod
    def _seconds(inputs):
        if isinstance(inputs, dict):
            return len(inputs["raw"]) / inputs["sampling_rate"]
        with wave.open(inputs, "rb") as wav:
            return wav.getnframes() / wav.getframerate()

    def __call__(self, inputs, *, return_timestamps, generate_kwargs):
        self.calls.append(return_timestamps)
        if self._seconds(inputs) > 30 and not return_timestamps:
            raise ValueError(LONG_FORM_ERROR)
        return {
            "text": " first second",
            "chunks": [{"text": " first", "timestamp": (0.0, 20.0)}, {"text": " second", "timestamp": (20.0, None)}],
        }


def _tone_wav(path, seconds, rate=16_000):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(
            b"".join(
                struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(int(rate * seconds))
            )
        )


@pytest.fixture
def long_wav(tmp_path):
    path = tmp_path / "long.wav"
    _tone_wav(path, 35)
    return path


@pytest.fixture
def short_wav(tmp_path):
    path = tmp_path / "short.wav"
    _tone_wav(path, 3)
    return path


# ── item 1: > 30 s ────────────────────────────────────────────────────────────


def test_array_over_30s_uses_long_form_and_short_keeps_return_timestamps_false():
    pipe = LongFormEnforcingPipe()
    assert audio_pipeline.transcribe_array(pipe, [0.0] * 16_000 * 40, 16_000).text == "first second"
    assert pipe.calls == [True]
    short = LongFormEnforcingPipe()
    audio_pipeline.transcribe_array(short, [0.0] * 16_000 * 10, 16_000)
    assert short.calls == [False]


def test_wav_over_30s_goes_long_form_by_duration_and_short_does_not(long_wav, short_wav):
    pipe = LongFormEnforcingPipe()
    assert audio_pipeline.transcribe_path(pipe, str(long_wav)).text == "first second"
    assert pipe.calls == [True]  # decided from the duration: no failed short-form attempt first
    short = LongFormEnforcingPipe()
    audio_pipeline.transcribe_path(short, str(short_wav))
    assert short.calls == [False]


def test_the_long_form_decision_does_not_read_the_error_text(long_wav):
    pipe = MagicMock(return_value={"text": "ok"})
    audio_pipeline.transcribe_path(pipe, str(long_wav))
    assert pipe.call_args.kwargs["return_timestamps"] is True


def test_wav_value_errors_are_never_retried(short_wav):
    pipe = MagicMock(side_effect=ValueError(LONG_FORM_ERROR))
    with pytest.raises(ValueError):
        audio_pipeline.transcribe_path(pipe, str(short_wav))
    assert pipe.call_count == 1


def test_a_container_retries_long_form_once_whatever_the_message(tmp_path):
    container = tmp_path / "clip.webm"
    container.write_bytes(b"\x1a\x45\xdf\xa3")
    pipe = MagicMock(side_effect=[ValueError("anything"), {"text": "ok"}])
    assert audio_pipeline.transcribe_path(pipe, str(container)).text == "ok"
    assert [c.kwargs["return_timestamps"] for c in pipe.call_args_list] == [False, True]
    failing = MagicMock(side_effect=ValueError("something else"))
    with pytest.raises(ValueError, match="something else"):
        audio_pipeline.transcribe_path(failing, str(container))
    assert failing.call_count == 2


@pytest.mark.asyncio
async def test_provider_handles_long_audio_with_real_chunk_times(long_wav):
    pipe = LongFormEnforcingPipe()
    with patch("voice_processing.providers.whisper_provider.get_whisper_pipeline", return_value=pipe):
        segments = await WhisperProvider().transcribe(str(long_wav), "en")
    assert pipe.calls == [True]
    assert [(s.text, s.start_time, s.end_time) for s in segments] == [("first", 0.0, 20.0), ("second", 20.0, 20.0)]


# ── item 3: no blocking load on the loop ──────────────────────────────────────


def test_is_available_never_calls_the_loader(monkeypatch):
    loader = MagicMock(side_effect=AssertionError("is_available must not load the model"))
    monkeypatch.setattr("voice_processing.providers.whisper_provider.get_whisper_pipeline", loader)
    monkeypatch.setattr(audio_pipeline, "_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(audio_pipeline, "_whisper_retry_at", 0.0)
    assert WhisperProvider().is_available() is True
    monkeypatch.setattr(audio_pipeline, "_TRANSFORMERS_AVAILABLE", False)
    assert WhisperProvider().is_available() is False
    loader.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_runs_the_blocking_work_in_a_worker_thread(short_wav):
    import threading

    seen = {}
    main = threading.get_ident()

    def loader():
        seen["thread"] = threading.get_ident()
        return LongFormEnforcingPipe()

    with patch("voice_processing.providers.whisper_provider.get_whisper_pipeline", side_effect=loader):
        await WhisperProvider().transcribe(str(short_wav), "en")
    assert seen["thread"] != main


# ── item 4: the loader does not latch, and integrity is not swallowed ─────────


@pytest.fixture
def fresh_loader(monkeypatch):
    monkeypatch.setattr(audio_pipeline, "_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(audio_pipeline, "_whisper_pipeline", None)
    monkeypatch.setattr(audio_pipeline, "_whisper_retry_at", 0.0)
    monkeypatch.setattr(audio_pipeline, "_whisper_integrity_error", None)
    return monkeypatch


def test_a_transient_load_failure_is_retried_after_the_window(fresh_loader):
    sentinel = object()
    loader = MagicMock(side_effect=[RuntimeError("network blip"), (sentinel,)])
    fresh_loader.setattr("autobot_shared.pinned_model_registry.load_verified", loader)
    assert audio_pipeline.get_whisper_pipeline() is None
    assert audio_pipeline.get_whisper_pipeline() is None and loader.call_count == 1  # inside the window
    assert audio_pipeline.whisper_loadable() is False
    fresh_loader.setattr(audio_pipeline, "_whisper_retry_at", 0.0)  # window elapsed
    assert audio_pipeline.get_whisper_pipeline() is sentinel


def test_integrity_failure_raises_every_time_and_is_never_retried(fresh_loader):
    loader = MagicMock(side_effect=ModelIntegrityError("tampered"))
    fresh_loader.setattr("autobot_shared.pinned_model_registry.load_verified", loader)
    for _ in range(2):
        with pytest.raises(ModelIntegrityError):
            audio_pipeline.get_whisper_pipeline()
    assert loader.call_count == 1
    assert audio_pipeline.whisper_loadable() is True  # surfaced, not reported as merely absent


# ── items 2 and 5: the fallback contract ──────────────────────────────────────


def _fake(name, *, segments=None, available=True, error=None):
    provider = create_autospec(SpeechProvider, instance=True, spec_set=True)
    type(provider).provider_name = name
    provider.is_available.return_value = available
    provider.is_external = False
    provider.external_when_local_unavailable = False
    provider.is_default_local = False
    if error is not None:
        provider.transcribe.side_effect = error
    else:
        provider.transcribe.return_value = [] if segments is None else segments
    return provider


def _registry(*providers):
    registry = SpeechProviderRegistry()
    for priority, provider in enumerate(reversed(providers)):
        registry.register("en", provider, priority=priority)
    return registry


@pytest.mark.asyncio
async def test_a_provider_that_ran_and_found_nothing_is_a_genuine_empty_and_ends_the_chain():
    first, second = _fake("a"), _fake("b")
    outcome = await _registry(first, second).transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is first and outcome.segments == []
    second.transcribe.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "providers, reasons",
    [
        ((_fake("a", available=False), _fake("b", available=False)), ["a: unavailable", "b: unavailable"]),
        (
            (_fake("a", error=RuntimeError("boom")), _fake("b", error=RuntimeError("x"))),
            ["a: RuntimeError", "b: RuntimeError"],
        ),
    ],
)
async def test_nobody_could_run_is_a_failure(providers, reasons):
    with pytest.raises(TranscriptionUnavailableError) as caught:
        await _registry(*providers).transcribe_with_fallback("a.wav", "en")
    assert caught.value.reasons == reasons


@pytest.mark.asyncio
async def test_integrity_error_does_not_fall_through_and_is_logged_at_error():
    second = _fake("cloud", segments=[TranscriptSegment("x", 0.0, 0.0, 0.9)])
    registry = _registry(_fake("local", error=ModelIntegrityError("tampered")), second)
    with patch.object(registry_logger, "error") as log_error:
        with pytest.raises(ModelIntegrityError):
            await registry.transcribe_with_fallback("a.wav", "en")
    second.transcribe.assert_not_called()
    assert log_error.called


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TypeError("bug"), AttributeError("bug"), NameError("bug")])
async def test_programming_errors_propagate(error):
    second = _fake("next", segments=[TranscriptSegment("x", 0.0, 0.0, 0.9)])
    with pytest.raises(type(error)):
        await _registry(_fake("a", error=error), second).transcribe_with_fallback("a.wav", "en")
    second.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_a_provider_failure_is_logged_with_its_traceback():
    registry = _registry(_fake("a", error=RuntimeError("boom")), _fake("b", segments=[TranscriptSegment("x", 0, 0, 1)]))
    with patch.object(registry_logger, "warning") as warn:
        await registry.transcribe_with_fallback("a.wav", "en")
    assert warn.call_args.kwargs.get("exc_info") is True


# ── a failed first load is a failure, not "no speech" ─────────────────────────


@pytest.mark.asyncio
async def test_a_loader_returning_none_raises_instead_of_yielding_an_empty_transcript(short_wav):
    from voice_processing.providers.whisper_provider import WhisperUnavailableError

    with patch("voice_processing.providers.whisper_provider.get_whisper_pipeline", return_value=None):
        with pytest.raises(WhisperUnavailableError):
            await WhisperProvider().transcribe(str(short_wav), "en")


@pytest.mark.asyncio
async def test_the_registry_records_the_whisper_load_failure_as_a_reason(short_wav):
    registry = SpeechProviderRegistry()
    registry.register("en", WhisperProvider(), priority=1)
    with (
        patch("voice_processing.providers.whisper_provider.whisper_loadable", return_value=True),
        patch("voice_processing.providers.whisper_provider.get_whisper_pipeline", return_value=None),
    ):
        with pytest.raises(TranscriptionUnavailableError) as caught:
            await registry.transcribe_with_fallback(str(short_wav), "en")
    assert caught.value.reasons == ["Whisper (local, pinned): WhisperUnavailableError"]
