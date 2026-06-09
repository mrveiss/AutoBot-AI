# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for voice API 503 guard (#3848).

Verifies that /api/voice/listen and /api/voice/speak return HTTP 503
(not AttributeError / 500) when app.state.voice_interface is not initialized.
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


def _make_app(*, with_voice_interface: bool) -> FastAPI:
    """Build a minimal FastAPI app wired with (or without) voice_interface."""
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    app.state.security_layer = _MockSecurityLayer()
    if with_voice_interface:
        # Use a simple sentinel object — the actual backend methods are not called
        # in these guard tests.
        app.state.voice_interface = object()
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

    def test_speak_returns_503_when_interface_absent(self):
        """POST /api/voice/speak must return 503 (not 500/AttributeError)."""
        app = _make_app(with_voice_interface=False)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/voice/speak", data={"text": "hello", "user_role": "user"})
        assert response.status_code == 503
        body = response.json()
        assert "message" in body
        assert "not available" in body["message"].lower()

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
        """Confirm AttributeError is not raised for /speak either."""
        app = _make_app(with_voice_interface=False)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post("/api/voice/speak", data={"text": "hello", "user_role": "user"})
        assert response.status_code == 503
