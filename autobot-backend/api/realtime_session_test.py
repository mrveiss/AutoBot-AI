# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    """Build a minimal FastAPI app with just the realtime_session router.

    The router is gated (#16375), so the gate is overridden here: these tests are
    about SDP proxying and provider selection, not about who may call them. What
    the gate actually is gets asserted directly in TestRouterIsGated below, which
    reads the router's declared dependencies instead of round-tripping HTTP --
    a request-level assertion would depend on whichever auth singleton a sibling
    test left installed.
    """
    from api.realtime_session import router
    from api.user_management.dependencies import get_current_user
    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(router, prefix="/api/voice/realtime")
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user", "username": "test"}
    app.dependency_overrides[check_admin_permission] = lambda: True
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
    """Return a mock aiohttp response, itself the tracked_request() async CM.

    #12979: OpenAIRealtimeProvider._post() now routes through the shared
    pool's get_http_client().tracked_request() rather than a private
    ClientSession, so this is patched directly (see _patch_http_client())
    instead of patching aiohttp.ClientSession.
    """
    resp = MagicMock()
    resp.status = status
    resp.read = AsyncMock(return_value=body)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _patch_http_client(upstream_cm):
    """Patch the shared HTTPClientManager singleton's tracked_request()."""
    from autobot_shared.http_client import get_http_client

    return patch.object(get_http_client(), "tracked_request", return_value=upstream_cm)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    """GH#7342 — valid SDP offer proxied successfully to OpenAI."""

    def test_returns_200(self, client: TestClient):
        upstream_cm = _mock_upstream(200, _SDP_ANSWER)
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-test-key"
            ),
            http_client_patch,
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 200

    def test_returns_sdp_content_type(self, client: TestClient):
        upstream_cm = _mock_upstream(200, _SDP_ANSWER)
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-test-key"
            ),
            http_client_patch,
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert "application/sdp" in resp.headers.get("content-type", "")

    def test_returns_upstream_body(self, client: TestClient):
        upstream_cm = _mock_upstream(200, _SDP_ANSWER)
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-test-key"
            ),
            http_client_patch,
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.content == _SDP_ANSWER

    def test_accepts_201_from_upstream(self, client: TestClient):
        upstream_cm = _mock_upstream(201, _SDP_ANSWER)
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-test-key"
            ),
            http_client_patch,
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
        with patch("voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value=""):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 503

    def test_missing_key_error_body(self, client: TestClient):
        with patch("voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value=""):
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
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-bad-key"
            ),
            http_client_patch,
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 502

    def test_upstream_401_error_body(self, client: TestClient):
        upstream_cm = _mock_upstream(401, b'{"error":"unauthorized"}')
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-bad-key"
            ),
            http_client_patch,
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
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-test-key"
            ),
            http_client_patch,
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        assert resp.status_code == 502, f"Expected 502 for upstream {status}, got {resp.status_code}"

    def test_upstream_5xx_error_body(self, client: TestClient):
        upstream_cm = _mock_upstream(500, b"oops")
        http_client_patch = _patch_http_client(upstream_cm)

        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key", return_value="sk-test-key"
            ),
            http_client_patch,
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )

        body = resp.json()
        assert body.get("detail", {}).get("success") is False


# ---------------------------------------------------------------------------
# Multi-provider dispatch + providers endpoints (Issue #9025)
# ---------------------------------------------------------------------------


class TestProviderDispatch:
    """#9025 — /session dispatches through the selected provider; default unchanged."""

    def test_session_header_advertises_provider(self, client: TestClient):
        upstream_cm = _mock_upstream(200, _SDP_ANSWER)
        http_client_patch = _patch_http_client(upstream_cm)
        with (
            patch(
                "voice_processing.realtime.openai_provider.OpenAIRealtimeProvider._api_key",
                return_value="sk-test-key",
            ),
            http_client_patch,
        ):
            resp = client.post(
                "/api/voice/realtime/session",
                data={"sdp": _SDP_OFFER, "session": _SESSION_JSON},
            )
        assert resp.status_code == 200
        assert resp.headers.get("x-realtime-provider") == "openai"


class TestProvidersEndpoint:
    """#9025 — GET/PATCH /providers list + select (never leaks credentials)."""

    def test_list_providers_default_openai(self, client: TestClient):
        resp = client.get("/api/voice/realtime/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["selected"] == "openai"
        ids = {p["id"] for p in body["providers"]}
        assert {"openai", "gemini", "elevenlabs", "ultravox"} <= ids
        # no credential leakage
        assert "api_key" not in resp.text and "key" not in {k for p in body["providers"] for k in p}

    def test_patch_selects_then_clears(self, client: TestClient):
        resp = client.patch("/api/voice/realtime/providers", json={"provider": "gemini"})
        assert resp.status_code == 200
        assert resp.json()["selected"] == "gemini"
        # clear back to default
        resp = client.patch("/api/voice/realtime/providers", json={"provider": None})
        assert resp.status_code == 200
        assert resp.json()["selected"] == "openai"

    def test_patch_unknown_provider_422(self, client: TestClient):
        resp = client.patch("/api/voice/realtime/providers", json={"provider": "bogus"})
        assert resp.status_code == 422


class TestRouterIsGated:
    """#16375 -- these routes spend money and invoke tools; none of them is open.

    Asserted against the router's declared dependencies rather than a response
    code, because ``get_auth_middleware`` is a process-global singleton that
    sibling tests stub: a 200 here would say more about test order than about
    the gate.
    """

    @staticmethod
    def _deps(deps) -> set:
        """The dependency callables themselves, not their names.

        The repo's conftest installs an ``auth_middleware`` stub, so under pytest
        ``check_admin_permission.__name__`` is ``_check_admin_permission_stub``. A
        name assertion would therefore be checking the test double. Identity holds
        under the stub and in production alike, because the router and this test
        import the same symbol either way.
        """
        return {d.dependency for d in (deps or [])}

    def test_router_requires_authentication(self):
        from api.realtime_session import router
        from api.user_management.dependencies import get_current_user

        assert get_current_user in self._deps(router.dependencies)

    def test_patch_providers_requires_admin(self):
        """set_active_provider changes the provider for every session, not the caller's."""
        from api.realtime_session import router
        from auth_middleware import check_admin_permission

        patch_routes = [
            r
            for r in router.routes
            if getattr(r, "path", "") == "/providers" and "PATCH" in getattr(r, "methods", set())
        ]
        assert len(patch_routes) == 1, f"expected exactly one PATCH /providers, found {len(patch_routes)}"
        assert check_admin_permission in self._deps(patch_routes[0].dependencies)

    def test_tool_dispatch_is_not_reachable_anonymously(self):
        """POST /tools/call dispatches an arbitrary named MCP tool (#16375).

        It carries no gate of its own, so what protects it is the router-level
        dependency -- this asserts the route exists and that the gate reaches it.
        """
        from api.realtime_session import router
        from api.user_management.dependencies import get_current_user

        tool_routes = [r for r in router.routes if getattr(r, "path", "") == "/tools/call"]
        assert len(tool_routes) == 1
        assert get_current_user in self._deps(tool_routes[0].dependencies)
