# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Characterization of the one Whisper inference path (#17778, residuals of #17780).

Pins what ``/voice/transcribe`` -> ``media.audio.pipeline.transcribe_bytes`` hands
the ASR pipeline TODAY: the temp-file suffix per MIME type, ``generate_kwargs``,
``return_timestamps``, and the response shape. Later consolidation slices must
keep these passing; a change that alters what Whisper is fed has to say so here.

The fake pipeline is ``create_autospec`` of a class with the call signature the
code uses, so renaming or dropping a keyword reddens the test (the #17778
mock-discipline requirement) instead of being absorbed by a bare MagicMock.
"""

import os
from unittest.mock import create_autospec

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.voice import router as voice_router
from media.audio import pipeline as audio_pipeline
from media.audio.pipeline import WHISPER_MIME_SUFFIXES, transcribe_bytes
from security_layer import SecurityLayer

#: Union of the two pre-#17780 maps. Spelled out here, not derived from the
#: production dict, so dropping an entry there fails instead of falling back to .wav.
EXPECTED_SUFFIXES = {
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
}


class _AsrPipeline:
    """The call shape ``transcribe_bytes`` uses on a transformers ASR pipeline."""

    def __call__(self, inputs, *, return_timestamps=None, generate_kwargs=None):
        raise NotImplementedError


class RecordingAsr:
    """Autospec'd ASR pipeline that records the file it was handed."""

    def __init__(self, output=None):
        self.seen: list[dict] = []
        self.mock = create_autospec(_AsrPipeline, instance=True, spec_set=True)
        self.mock.side_effect = self._call
        self._output = {"text": " hello world "} if output is None else output

    def _call(self, inputs, *, return_timestamps=None, generate_kwargs=None):
        with open(inputs, "rb") as fh:
            payload = fh.read()
        self.seen.append(
            {
                "path": inputs,
                "suffix": os.path.splitext(inputs)[1],
                "payload": payload,
                "return_timestamps": return_timestamps,
                "generate_kwargs": generate_kwargs,
            }
        )
        return self._output


def test_the_mime_map_is_exactly_the_union_of_the_two_old_maps() -> None:
    assert WHISPER_MIME_SUFFIXES == EXPECTED_SUFFIXES


@pytest.mark.parametrize(("mime", "suffix"), sorted(EXPECTED_SUFFIXES.items()))
def test_temp_file_suffix_per_mime(mime: str, suffix: str) -> None:
    asr = RecordingAsr()
    transcribe_bytes(asr.mock, b"AUDIO", mime=mime)
    assert asr.seen[0]["suffix"] == suffix


@pytest.mark.parametrize("mime", ["audio/unknown", "video/mp4", ""])
def test_an_unknown_mime_falls_back_to_wav(mime: str) -> None:
    asr = RecordingAsr()
    transcribe_bytes(asr.mock, b"AUDIO", mime=mime)
    assert asr.seen[0]["suffix"] == ".wav"


def test_the_pipeline_is_handed_the_bytes_and_the_file_is_removed_after() -> None:
    asr = RecordingAsr()
    transcribe_bytes(asr.mock, b"AUDIO-BYTES", mime="audio/ogg")
    assert asr.seen[0]["payload"] == b"AUDIO-BYTES"
    assert not os.path.exists(asr.seen[0]["path"])


def test_a_language_hint_is_forwarded_as_generate_kwargs() -> None:
    asr = RecordingAsr()
    transcribe_bytes(asr.mock, b"A", mime="audio/wav", language="en")
    assert asr.seen[0]["generate_kwargs"] == {"language": "en"}


def test_no_language_hint_sends_no_generate_kwargs() -> None:
    asr = RecordingAsr()
    transcribe_bytes(asr.mock, b"A", mime="audio/wav", language="")
    assert asr.seen[0]["generate_kwargs"] is None


def test_timestamps_are_never_requested() -> None:
    asr = RecordingAsr()
    transcribe_bytes(asr.mock, b"A", mime="audio/wav")
    assert asr.seen[0]["return_timestamps"] is False


def test_the_output_is_stripped_and_defaults_are_unknown_language() -> None:
    result = transcribe_bytes(RecordingAsr().mock, b"A", mime="audio/wav")
    assert (result.text, result.language, result.chunks) == ("hello world", "unknown", [])


# ---- the /voice/transcribe response shape ---------------------------------


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    security = create_autospec(SecurityLayer, instance=True, spec_set=True)
    security.check_permission.return_value = True
    app.state.security_layer = security
    return TestClient(app, raise_server_exceptions=True)


def _post(client: TestClient, content_type: str = "audio/wav", language: str = ""):
    return client.post(
        "/api/voice/transcribe",
        files={"audio": ("clip", b"RIFFdata", content_type)},
        data={"language": language},
    )


def test_the_route_response_shape_for_recognised_speech(monkeypatch) -> None:
    asr = RecordingAsr({"text": "hello world", "language": "en"})
    monkeypatch.setattr(audio_pipeline, "get_whisper_pipeline", lambda: asr.mock)
    body = _post(_client(), language="en").json()
    assert body == {"text": "hello world", "language": "en", "confidence": 0.9}
    assert asr.seen[0]["generate_kwargs"] == {"language": "en"}


def test_the_route_confidence_floor_for_empty_text_is_zero(monkeypatch) -> None:
    asr = RecordingAsr({"text": "   "})
    monkeypatch.setattr(audio_pipeline, "get_whisper_pipeline", lambda: asr.mock)
    assert _post(_client()).json() == {"text": "", "language": "unknown", "confidence": 0.0}


def test_the_route_without_a_loaded_model_is_a_503_with_the_reason(monkeypatch) -> None:
    monkeypatch.setattr(audio_pipeline, "get_whisper_pipeline", lambda: None)
    response = _post(_client())
    assert response.status_code == 503
    assert "could not be loaded" in response.json()["detail"]


def test_the_route_strips_mime_parameters_before_choosing_the_suffix(monkeypatch) -> None:
    asr = RecordingAsr()
    monkeypatch.setattr(audio_pipeline, "get_whisper_pipeline", lambda: asr.mock)
    _post(_client(), content_type="audio/webm;codecs=opus")
    assert asr.seen[0]["suffix"] == ".webm"


def test_an_inference_failure_is_a_500_with_the_reason_not_an_empty_200(monkeypatch) -> None:
    asr = RecordingAsr()
    asr.mock.side_effect = RuntimeError("model fell over")
    monkeypatch.setattr(audio_pipeline, "get_whisper_pipeline", lambda: asr.mock)
    response = _post(_client())
    assert response.status_code == 500
    assert response.json()["detail"] == "Speech transcription failed"
