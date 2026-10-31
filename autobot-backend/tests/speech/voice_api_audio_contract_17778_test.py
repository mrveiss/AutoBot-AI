# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Characterization of the synthesis API's audio contract (#17778).

``/voice/speak`` and ``/voice/synthesize`` return the worker's WAV bytes
unchanged as ``audio/wav`` (or length-prefixed chunks when ``stream`` is set), and
``/voice/speak`` reports server-side playback through ``X-Server-Playback``
rather than the body (#17779). The voice id each request ends up synthesised with
comes from ``resolve_voice_id``, whose priority order is pinned below.
"""

from unittest.mock import create_autospec, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.voice import router as voice_router
from security_layer import SecurityLayer
from services.tts_client import TTSClient
from voice_interface import VoiceInterface


def _app(*, interface=None, allowed: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    security = create_autospec(SecurityLayer, instance=True, spec_set=True)
    security.check_permission.return_value = allowed
    app.state.security_layer = security
    if interface is not None:
        app.state.voice_interface = interface
    return app


def _tts(wav: bytes, chunks: list[bytes] | None = None):
    tts = create_autospec(TTSClient, instance=True, spec_set=True)
    tts.synthesize.return_value = wav

    async def _stream(text, voice_id="", language=""):
        for chunk in chunks or []:
            yield chunk

    tts.stream_or_synthesize.side_effect = _stream
    return tts


@pytest.fixture
def post(real_personality_service):
    """POST to a synthesis route with the TTS client and voice resolver spec'd."""

    def _post(app: FastAPI, route: str, tts, **form):
        resolver = create_autospec(real_personality_service.resolve_voice_id)
        resolver.return_value = "RESOLVED"
        with patch("api.voice.get_tts_client", return_value=tts), patch("api.voice.resolve_voice_id", resolver):
            response = TestClient(app).post(f"/api/voice/{route}", data={"text": "hello", **form})
        return response, resolver

    return _post


@pytest.mark.parametrize("route", ["speak", "synthesize"])
def test_the_whole_utterance_is_the_workers_wav_unchanged(route, fixture_wav, post) -> None:
    tts = _tts(fixture_wav)
    response, resolver = post(_app(), route, tts, voice_id="alba", language="en")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["content-disposition"] == "attachment; filename=speech.wav"
    assert response.content == fixture_wav
    resolver.assert_called_once_with("alba", "en")
    tts.synthesize.assert_awaited_once_with("hello", voice_id="RESOLVED", language="en")


@pytest.mark.parametrize("route", ["speak", "synthesize"])
def test_stream_returns_length_prefixed_wav_chunks_with_a_framing_header(route, make_wav, post) -> None:
    chunks = [make_wav(frames=240), make_wav(frames=480)]
    response, _ = post(_app(), route, _tts(b"", chunks), stream="true")
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-audio-framing"] == "length-prefixed-wav"
    assert response.content == b"".join(len(c).to_bytes(4, "big") + c for c in chunks)


def test_speak_reports_playback_not_requested_by_default(fixture_wav, post) -> None:
    response, _ = post(_app(), "speak", _tts(fixture_wav))
    assert response.headers["x-server-playback"] == "not-requested"


def test_synthesize_has_no_playback_header(fixture_wav, post) -> None:
    response, _ = post(_app(), "synthesize", _tts(fixture_wav))
    assert "x-server-playback" not in response.headers


def test_play_locally_without_a_local_interface_is_unavailable_but_still_audio(fixture_wav, post) -> None:
    response, _ = post(_app(), "speak", _tts(fixture_wav), play_locally="true")
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-server-playback"] == "unavailable"
    assert response.content == fixture_wav


@pytest.mark.parametrize(("status", "header"), [("success", "played"), ("error", "failed")])
def test_play_locally_reports_the_local_outcome_in_the_header(status, header, fixture_wav, post) -> None:
    interface = create_autospec(VoiceInterface, instance=True, spec_set=True)
    interface.speak_text.return_value = {"status": status, "message": "m"}
    response, _ = post(_app(interface=interface), "speak", _tts(fixture_wav), play_locally="true")
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-server-playback"] == header
    interface.speak_text.assert_awaited_once_with("hello")


def test_play_locally_cannot_be_combined_with_stream(fixture_wav, post) -> None:
    response, _ = post(_app(), "speak", _tts(fixture_wav), play_locally="true", stream="true")
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize("route", ["speak", "synthesize"])
def test_a_denied_caller_gets_json_403_and_no_synthesis(route, fixture_wav, post) -> None:
    tts = _tts(fixture_wav)
    response, _ = post(_app(allowed=False), route, tts)
    assert response.status_code == 403
    tts.synthesize.assert_not_awaited()


# ---- resolve_voice_id priority --------------------------------------------


@pytest.fixture
def with_profile(real_personality_service):
    """Make the real ``resolve_voice_id`` see *profile* as the active one."""
    module = real_personality_service

    def _with(profile):
        manager = create_autospec(module.PersonalityManager, instance=True, spec_set=True)
        manager.get_active_profile.return_value = profile
        return patch.object(module, "get_personality_manager", return_value=manager)

    return _with


@pytest.fixture
def profile(real_personality_service):
    return real_personality_service.PersonalityProfile(
        id="p", name="P", voice_id="profile-voice", voice_ids={"lv": "lv-voice"}
    )


@pytest.mark.parametrize(
    ("request_voice", "language", "expected"),
    [
        ("explicit", "lv", "explicit"),
        ("", "lv", "lv-voice"),
        ("", "en", "profile-voice"),
        ("", "", "profile-voice"),
    ],
)
def test_voice_priority_request_then_profile_per_language_then_profile(
    real_personality_service, with_profile, profile, request_voice, language, expected
) -> None:
    with with_profile(profile):
        assert real_personality_service.resolve_voice_id(request_voice, language) == expected


def test_a_profile_with_no_voice_resolves_to_the_empty_default(real_personality_service, with_profile) -> None:
    with with_profile(real_personality_service.PersonalityProfile(id="p", name="P")):
        assert real_personality_service.resolve_voice_id("", "en") == ""


def test_no_active_profile_resolves_to_the_empty_default(real_personality_service, with_profile) -> None:
    with with_profile(None):
        assert real_personality_service.resolve_voice_id("", "en") == ""


def test_a_failing_profile_lookup_resolves_to_the_empty_default(real_personality_service) -> None:
    module = real_personality_service
    manager = create_autospec(module.PersonalityManager, instance=True, spec_set=True)
    manager.get_active_profile.side_effect = RuntimeError("store down")
    with patch.object(module, "get_personality_manager", return_value=manager):
        assert module.resolve_voice_id("", "en") == ""
