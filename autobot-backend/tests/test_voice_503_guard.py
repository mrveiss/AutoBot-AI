# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Voice API behaviour when ``app.state.voice_interface`` is absent (#3848), and
``/speak``'s single response shape (#17779).

Originally both routes 503'd rather than raising ``AttributeError``. ``/speak``
stopped doing that at #10561 -- the canonical TTS is the pocket-tts worker, which
is always available, so a 503 there implied TTS was uninstalled when it was not.
``/listen`` still 503s, because speech *recognition* has no worker fallback.

The file name is kept: the 503 guard is still what the ``/listen`` half asserts,
and renaming it would detach these tests from #3848 in every search that finds
them by name.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.voice import router as voice_router


class _MockSecurityLayer:
    """Minimal security_layer stub that always permits."""

    def check_permission(self, role: str, permission: str) -> bool:
        return True

    def audit_log(self, *args, **kwargs) -> None:
        pass


def _make_app(*, with_voice_interface: bool, interface=None) -> FastAPI:
    """Build a minimal FastAPI app wired with (or without) voice_interface.

    ``interface`` supplies a real stub for the tests that exercise server-side
    playback (#17779); the older guard tests pass nothing and keep the sentinel,
    because they only need the attribute to exist.
    """
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    app.state.security_layer = _MockSecurityLayer()
    if with_voice_interface:
        # Use a simple sentinel object — the actual backend methods are not called
        # in these guard tests.
        app.state.voice_interface = interface if interface is not None else object()
    else:
        # Explicitly absent — simulates the bug described in #3848.
        # (app.state has no voice_interface attribute at all)
        pass
    return app


class TestVoice503Guard:
    """Ensure voice endpoints return 503 when voice_interface is absent."""

    def test_listen_returns_503_when_interface_absent(self):
        """POST /api/voice/listen must return 503 (not 500/AttributeError)."""
        app = _make_app(with_voice_interface=False)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/voice/listen", data={"user_role": "user"})
        assert response.status_code == 503
        body = response.json()
        assert "message" in body
        assert "not available" in body["message"].lower()

    def test_speak_synthesizes_via_worker_when_interface_absent(self):
        """POST /api/voice/speak now synthesizes via the TTS worker (200 audio/wav)
        when the optional local pyttsx3 voice_interface is absent — the canonical
        TTS is the pocket-tts worker, so a 503 here would be misleading (#10561)."""
        import unittest.mock as mock

        app = _make_app(with_voice_interface=False)
        client = TestClient(app, raise_server_exceptions=False)
        fake = mock.MagicMock()
        fake.synthesize = mock.AsyncMock(return_value=b"RIFFfakewavdata")
        with mock.patch("api.voice.get_tts_client", return_value=fake):
            response = client.post("/api/voice/speak", data={"text": "hello", "user_role": "user"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.content == b"RIFFfakewavdata"

    def test_listen_does_not_raise_attribute_error_when_interface_absent(self):
        """The old behaviour raised AttributeError (500). Confirm it no longer does."""
        app = _make_app(with_voice_interface=False)
        # raise_server_exceptions=True would re-raise server errors as exceptions;
        # use it here to confirm no exception propagates.
        client = TestClient(app, raise_server_exceptions=True)
        # Should not raise — the guard catches the missing attribute before it
        # reaches the AttributeError site.
        response = client.post("/api/voice/listen", data={"user_role": "user"})
        assert response.status_code == 503

    def test_speak_does_not_raise_attribute_error_when_interface_absent(self):
        """Confirm AttributeError is not raised for /speak when interface absent
        (it falls through to worker synthesis, not the AttributeError site)."""
        import unittest.mock as mock

        app = _make_app(with_voice_interface=False)
        client = TestClient(app, raise_server_exceptions=True)
        fake = mock.MagicMock()
        fake.synthesize = mock.AsyncMock(return_value=b"RIFFfakewavdata")
        with mock.patch("api.voice.get_tts_client", return_value=fake):
            response = client.post("/api/voice/speak", data={"text": "hello", "user_role": "user"})
        assert response.status_code == 200


class TestSpeakHasOneResponseShape:
    """#17779: `/speak` returned WAV **or** JSON depending on a boot accident.

    `app.state.voice_interface` is set inside a try/except at boot, so whether an
    optional pyttsx3 import succeeded decided the route's contract: absent meant
    `audio/wav` from the TTS worker, present meant `{"message": ...}` with no
    audio and playback on the SERVER's speakers. A client could not know which.

    These tests drive **both** boot states through the same route and require the
    same content type, so the fork cannot come back through a refactor.
    """

    @staticmethod
    def _tts(payload: bytes = b"RIFFfakewavdata"):
        import unittest.mock as mock

        fake = mock.MagicMock()
        fake.synthesize = mock.AsyncMock(return_value=payload)
        return fake

    @staticmethod
    def _interface(status: str = "success"):
        import unittest.mock as mock

        iface = mock.MagicMock()
        iface.speak_text = mock.AsyncMock(return_value={"status": status, "message": "pyttsx3 says no"})
        return iface

    def _post(self, app, **extra):
        import unittest.mock as mock

        client = TestClient(app, raise_server_exceptions=False)
        with mock.patch("api.voice.get_tts_client", return_value=self._tts()):
            return client.post("/api/voice/speak", data={"text": "hello", "user_role": "user", **extra})

    def test_speak_returns_wav_when_the_interface_is_present(self):
        """The branch that used to return JSON. This is the defect, directly."""
        response = self._post(_make_app(with_voice_interface=True, interface=self._interface()))
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.content == b"RIFFfakewavdata"

    def test_both_boot_states_produce_the_same_content_type(self):
        """The anti-regression pin the fork's return would trip first."""
        present = self._post(_make_app(with_voice_interface=True, interface=self._interface()))
        absent = self._post(_make_app(with_voice_interface=False))
        assert present.headers["content-type"] == absent.headers["content-type"] == "audio/wav"
        assert present.status_code == absent.status_code == 200
        assert present.content == absent.content

    def test_server_playback_is_off_by_default(self):
        """Playing on the server's speakers is now opt-in, so a plain call must not."""
        iface = self._interface()
        response = self._post(_make_app(with_voice_interface=True, interface=iface))
        iface.speak_text.assert_not_awaited()
        assert response.headers["X-Server-Playback"] == "not-requested"

    def test_play_locally_speaks_without_changing_the_shape(self):
        iface = self._interface()
        response = self._post(_make_app(with_voice_interface=True, interface=iface), play_locally="true")
        iface.speak_text.assert_awaited_once_with("hello")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.headers["X-Server-Playback"] == "played"
        assert response.content == b"RIFFfakewavdata"

    def test_play_locally_reports_failure_without_changing_the_shape(self):
        """A playback failure used to be a 500 with a JSON body. The caller asked
        for audio and still gets audio; the outcome moves to the header."""
        iface = self._interface(status="error")
        response = self._post(_make_app(with_voice_interface=True, interface=iface), play_locally="true")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.headers["X-Server-Playback"] == "failed"

    def test_play_locally_reports_unavailable_when_there_is_no_interface(self):
        """Requesting playback on a boot where pyttsx3 is absent must not resurrect
        the fork: audio still comes back, and the header says playback did not."""
        response = self._post(_make_app(with_voice_interface=False), play_locally="true")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.headers["X-Server-Playback"] == "unavailable"

    def test_play_locally_with_stream_is_refused(self):
        """Streaming serves the caller; playback serves the server. One request
        cannot do both without making `stream` silently useless, so it is refused
        rather than quietly degraded."""
        iface = self._interface()
        response = self._post(_make_app(with_voice_interface=True, interface=iface), play_locally="true", stream="true")
        assert response.status_code == 400
        iface.speak_text.assert_not_awaited()
