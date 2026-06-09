# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SecurityHeadersMiddleware (Issue #2858).

Verifies that:
  - State-changing requests without Authorization header are rejected (401).
  - State-changing requests WITH Authorization header pass through.
  - Exempt paths (login, health) are not blocked even without a token.
  - Security response headers are present on all responses.
"""

import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# Ensure the slm-backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal test application
# ---------------------------------------------------------------------------


async def _ok(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


_routes = [
    Route("/api/nodes", _ok, methods=["GET", "POST", "DELETE"]),
    Route("/api/auth/login", _ok, methods=["POST"]),
    Route("/api/health", _ok, methods=["GET"]),
    Route("/api/api-keys/scopes", _ok, methods=["GET"]),
    Route("/api/events/sync", _ok, methods=["POST"]),
]

_app = Starlette(routes=_routes)
_app.add_middleware(SecurityHeadersMiddleware)
_client = TestClient(_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# CSRF enforcement tests
# ---------------------------------------------------------------------------


class TestCsrfEnforcement:
    """POST/PUT/PATCH/DELETE without Authorization header must be rejected."""

    def test_post_without_auth_is_rejected(self):
        response = _client.post("/api/nodes")
        assert response.status_code == 401
        assert "Authorization" in response.json()["detail"]

    def test_delete_without_auth_is_rejected(self):
        response = _client.delete("/api/nodes")
        assert response.status_code == 401

    def test_post_with_auth_passes_through(self):
        response = _client.post("/api/nodes", headers={"Authorization": "Bearer fake.jwt.token"})
        assert response.status_code == 200

    def test_delete_with_auth_passes_through(self):
        response = _client.delete("/api/nodes", headers={"Authorization": "Bearer fake.jwt.token"})
        assert response.status_code == 200

    def test_get_without_auth_passes_through(self):
        """GET is read-only — must not be blocked."""
        response = _client.get("/api/nodes")
        assert response.status_code == 200


class TestExemptPaths:
    """Unauthenticated paths must never be blocked."""

    def test_login_post_without_auth_passes(self):
        response = _client.post("/api/auth/login")
        assert response.status_code == 200

    def test_health_get_passes(self):
        response = _client.get("/api/health")
        assert response.status_code == 200

    def test_scopes_get_passes(self):
        response = _client.get("/api/api-keys/scopes")
        assert response.status_code == 200

    def test_events_sync_post_without_auth_passes(self):
        """Agent event sync must not be blocked — node_id validated in endpoint (#3193)."""
        response = _client.post("/api/events/sync")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Security header tests
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    """All responses must carry the required security headers."""

    def _get_headers(self) -> dict:
        return _client.get("/api/health").headers

    @pytest.mark.parametrize(
        "header,expected",
        [
            ("x-frame-options", "DENY"),
            ("x-content-type-options", "nosniff"),
            ("x-xss-protection", "0"),
            ("referrer-policy", "strict-origin-when-cross-origin"),
            ("content-security-policy", "default-src 'none'"),
        ],
    )
    def test_security_header_present(self, header: str, expected: str):
        headers = self._get_headers()
        assert header in headers, f"Missing header: {header}"
        assert headers[header] == expected, f"Header {header!r}: expected {expected!r}, got {headers[header]!r}"

    def test_hsts_header_present(self):
        headers = self._get_headers()
        assert "strict-transport-security" in headers
        assert "max-age=31536000" in headers["strict-transport-security"]

    def test_security_headers_on_rejected_request(self):
        """Rejected CSRF requests must also carry security headers."""
        response = _client.post("/api/nodes")
        assert response.status_code == 401
        assert "x-frame-options" in response.headers
        assert "x-content-type-options" in response.headers
