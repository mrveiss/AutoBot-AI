# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pytest tests for the backend SDP proxy endpoint (GH#7342).

Covers:
  - Happy path: mocked aiohttp upstream returns 200 + SDP body
  - Missing key: 503 when no OPENAI_API_KEY is configured
  - Upstream 401: mapped to 502
  - Upstream 5xx: mapped to 502
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Minimal test app — avoids importing the full AutoBot stack
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with just the realtime_session router."""
    from api.realtime_session import router

    app = FastAPI()
    app.include_router(router, prefix="/api/voice/realtime")
    return app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SDP_OFFER = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"
_SESSION_JSON = '{"model":"gpt-realtime-2"}'
_SDP_ANSWER = b"v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"


def _form(sdp: str = _SDP_OFFER, session: str = _SESSION_JSON) -> dict:
    return {"sdp": (None, sdp), "session": (None, session)}


def _mock_upstream(status: int = 200, body: bytes = _SDP_ANSWER):
    """Return a mock aiohttp response context-manager."""
    resp = MagicMock()
    resp.status = status
    resp.read = AsyncMock(return_value=body)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_session(upstream_cm):
    """Return a mock aiohttp.ClientSession context-manager."""
    session = MagicMock()
    session.post = MagicMock(return_value=upstream_cm)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return session_cm


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    """GH#7342 — valid SDP offer proxied successfully to OpenAI."""

    def test_returns_200(self, client: TestClient):
        upstream_cm = _mock_upstream(200, _SDP_ANSWER)
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-test-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 200

    def test_returns_sdp_content_type(self, client: TestClient):
        upstream_cm = _mock_upstream(200, _SDP_ANSWER)
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-test-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert "application/sdp" in resp.headers.get("content-type", "")

    def test_returns_upstream_body(self, client: TestClient):
        upstream_cm = _mock_upstream(200, _SDP_ANSWER)
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-test-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.content == _SDP_ANSWER

    def test_accepts_201_from_upstream(self, client: TestClient):
        upstream_cm = _mock_upstream(201, _SDP_ANSWER)
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-test-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Missing API key → 503
# ---------------------------------------------------------------------------


class TestMissingApiKey:
    """GH#7342 — no OPENAI_API_KEY configured must return 503."""

    def test_missing_key_returns_503(self, client: TestClient):
        with patch("api.realtime_session._get_api_key", return_value=""):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 503

    def test_missing_key_error_body(self, client: TestClient):
        with patch("api.realtime_session._get_api_key", return_value=""):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        body = resp.json()
        assert body.get("detail", {}).get("success") is False


# ---------------------------------------------------------------------------
# Upstream 401 → 502
# ---------------------------------------------------------------------------


class TestUpstream401:
    """GH#7342 — upstream 401 must be mapped to 502."""

    def test_upstream_401_returns_502(self, client: TestClient):
        upstream_cm = _mock_upstream(401, b'{"error":"unauthorized"}')
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-bad-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 502

    def test_upstream_401_error_body(self, client: TestClient):
        upstream_cm = _mock_upstream(401, b'{"error":"unauthorized"}')
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-bad-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        body = resp.json()
        assert body.get("detail", {}).get("success") is False


# ---------------------------------------------------------------------------
# Upstream 5xx → 502
# ---------------------------------------------------------------------------


class TestUpstream5xx:
    """GH#7342 — upstream 5xx must be mapped to 502."""

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_upstream_5xx_returns_502(self, client: TestClient, status: int):
        upstream_cm = _mock_upstream(status, b"internal server error")
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-test-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 502, f"Expected 502 for upstream {status}, got {resp.status_code}"

    def test_upstream_5xx_error_body(self, client: TestClient):
        upstream_cm = _mock_upstream(500, b"oops")
        session_cm = _mock_session(upstream_cm)

        with (
            patch("api.realtime_session._get_api_key", return_value="sk-test-key"),
            patch("aiohttp.ClientSession", return_value=session_cm),
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        body = resp.json()
        assert body.get("detail", {}).get("success") is False
