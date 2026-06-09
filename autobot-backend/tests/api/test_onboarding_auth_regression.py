# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for GH #6568 — /api/onboarding auth enforcement.

Linked issue: https://github.com/mrveiss/AutoBot-AI/issues/6568

Fix applied: commit 9db25020a auth-gates the three privileged endpoints:
  - GET  /api/onboarding/presets  → Depends(get_current_user)
  - GET  /api/onboarding/doctor   → Depends(get_current_user)
  - POST /api/onboarding/apply    → Depends(check_admin_permission)
  - GET  /api/onboarding/status   → intentionally open (no auth dep)

Regression guarantee: if Depends(...) is removed from any protected route,
the corresponding test will fail because the endpoint will return 2xx/5xx
instead of the expected 401.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

# ── stub auth_middleware with proper FastAPI-compatible functions ─────────────
# FastAPI inspects dependency signatures via inspect.signature(). MagicMock
# has a non-inspectable signature that causes FastAPI to raise 422. Use real
# functions instead.


def _stub_check_admin_permission(request: Request) -> bool:
    """Default stub: approves all requests (overridden per-test via dependency_overrides)."""
    return True


def _stub_get_current_user(request: Request) -> dict:
    """Default stub: returns synthetic admin user (overridden per-test)."""
    return {"username": "test-admin", "role": "admin"}


if "auth_middleware" not in sys.modules:
    _auth_stub = types.ModuleType("auth_middleware")
    _auth_stub.check_admin_permission = _stub_check_admin_permission
    _auth_stub.get_current_user = _stub_get_current_user
    _auth_stub.get_auth_middleware = MagicMock()
    _auth_stub.raise_auth_error = MagicMock(side_effect=HTTPException(status_code=401))
    sys.modules["auth_middleware"] = _auth_stub

# Stub onboarding.doctor to avoid psutil import at test-collection time.
if "onboarding.doctor" not in sys.modules:
    _doctor_stub = types.ModuleType("onboarding.doctor")
    _doctor_stub.run_doctor = AsyncMock(return_value={"status": "ok"})
    sys.modules["onboarding.doctor"] = _doctor_stub

# ── import the real onboarding router (fix applied — has auth deps) ───────────
from api.onboarding import router as _onboarding_router  # noqa: E402

# ── test helpers ──────────────────────────────────────────────────────────────


def _raise_401() -> None:
    """Simulates an unauthenticated request — returns 401 like the real deps would."""
    raise HTTPException(status_code=401, detail="Authentication required")


def _allow_user() -> dict:
    return {"username": "test-admin", "role": "admin"}


def _allow_admin() -> bool:
    return True


def _make_unauthenticated_client() -> TestClient:
    """TestClient that overrides BOTH auth deps to reject all requests."""
    app = FastAPI()
    app.include_router(_onboarding_router, prefix="/api/onboarding")
    from auth_middleware import check_admin_permission, get_current_user

    app.dependency_overrides[get_current_user] = _raise_401
    app.dependency_overrides[check_admin_permission] = _raise_401
    return TestClient(app, raise_server_exceptions=False)


def _make_authenticated_client() -> TestClient:
    """TestClient that overrides both auth deps to allow all requests."""
    app = FastAPI()
    app.include_router(_onboarding_router, prefix="/api/onboarding")
    from auth_middleware import check_admin_permission, get_current_user

    app.dependency_overrides[get_current_user] = _allow_user
    app.dependency_overrides[check_admin_permission] = _allow_admin
    return TestClient(app, raise_server_exceptions=False)


# ── GH #6568 regression: protected routes must enforce auth ──────────────────


class TestOnboardingAuthEnforcement:
    """Privileged endpoints must reject unauthenticated requests.

    Each test overrides the relevant auth dependency to raise 401 and verifies
    that the endpoint returns 401. If the auth dependency is removed, the
    override has no effect, the endpoint runs its business logic, and the
    expected 401 is never returned — causing the assertion to fail.
    """

    def test_presets_returns_401_without_auth(self):
        """GET /presets must require auth via get_current_user — GH #6568."""
        client = _make_unauthenticated_client()
        resp = client.get("/api/onboarding/presets")
        assert resp.status_code == 401, (
            f"GET /api/onboarding/presets returned HTTP {resp.status_code}; expected 401. "
            "Regression (GH #6568): add Depends(get_current_user) to this route."
        )

    def test_doctor_returns_401_without_auth(self):
        """GET /doctor must require auth via get_current_user — GH #6568."""
        client = _make_unauthenticated_client()
        resp = client.get("/api/onboarding/doctor")
        assert resp.status_code == 401, (
            f"GET /api/onboarding/doctor returned HTTP {resp.status_code}; expected 401. "
            "Regression (GH #6568): add Depends(get_current_user) to this route."
        )

    def test_apply_returns_401_without_auth(self):
        """POST /apply must require auth via check_admin_permission — GH #6568."""
        client = _make_unauthenticated_client()
        resp = client.post(
            "/api/onboarding/apply",
            json={"preset_name": "chat-simple", "overrides": {}},
        )
        assert resp.status_code == 401, (
            f"POST /api/onboarding/apply returned HTTP {resp.status_code}; expected 401. "
            "Regression (GH #6568): add Depends(check_admin_permission) to this route."
        )


class TestOnboardingStatusIsOpen:
    """/status must remain intentionally open — called pre-login by the router guard."""

    def test_status_returns_200_without_auth(self):
        """/status must succeed even when other auth deps reject — GH #6568.

        The unauthenticated client overrides both auth deps to raise 401.
        /status carries no auth dependency, so neither override fires, and the
        endpoint returns its fail-open 200. If /status is accidentally auth-gated
        this test will see 401 and fail.
        """
        client = _make_unauthenticated_client()
        resp = client.get("/api/onboarding/status")
        assert resp.status_code == 200, (
            f"GET /api/onboarding/status returned HTTP {resp.status_code}; expected 200. "
            "Do NOT add auth to /status — it is intentionally open (GH #6568)."
        )


class TestOnboardingAuthenticatedSuccess:
    """Auth-gated endpoints must reach business logic when credentials are provided."""

    def test_presets_succeeds_when_authenticated(self):
        from unittest.mock import patch

        with patch("onboarding.presets.get_all_presets", return_value=[]):
            client = _make_authenticated_client()
            resp = client.get("/api/onboarding/presets")
        assert resp.status_code == 200

    def test_apply_404_for_unknown_preset_when_authenticated(self):
        """Auth passes → business logic executes → 404 for a missing preset."""
        from unittest.mock import patch

        with patch("onboarding.presets.get_preset", return_value=None):
            client = _make_authenticated_client()
            resp = client.post(
                "/api/onboarding/apply",
                json={"preset_name": "no-such-preset", "overrides": {}},
            )
        assert resp.status_code == 404
