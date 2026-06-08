# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression tests for GH #6568 — /api/onboarding auth enforcement.

Linked issue: https://github.com/mrveiss/AutoBot-AI/issues/6568

Fix applied: commit 9db25020a auth-gates the three privileged endpoints:
  - GET  /api/onboarding/presets  → Depends(get_current_user)
  - GET  /api/onboarding/doctor   → Depends(get_current_user)
  - POST /api/onboarding/apply    → Depends(check_admin_permission)
  - GET  /api/onboarding/status   → intentionally open (no auth dep)
                                    (frontend router guard calls before login)

Regression guarantee: if Depends(...) is removed from any protected route,
the corresponding test fails because the endpoint returns 2xx/5xx instead of
the expected 401. The dependency_overrides mechanism is key: it only fires
when the route actually declares the dependency — removing it silences the
override and lets business logic run unchecked.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

# ── stub auth_middleware before importing api.onboarding ─────────────────────
# FastAPI validates dependency signatures via inspect.signature(). MagicMock
# has an opaque signature that triggers 422. Use real typed functions instead.


def _stub_get_current_user(request: Request) -> dict:
    """Default stub: returns synthetic admin (overridden per-test via dependency_overrides)."""
    return {"username": "test-admin", "role": "admin"}


def _stub_check_admin_permission(request: Request) -> bool:
    """Default stub: approves all (overridden per-test via dependency_overrides)."""
    return True


if "auth_middleware" not in sys.modules:
    _auth_stub = types.ModuleType("auth_middleware")
    _auth_stub.get_current_user = _stub_get_current_user
    _auth_stub.check_admin_permission = _stub_check_admin_permission
    _auth_stub.get_auth_middleware = MagicMock()
    _auth_stub.raise_auth_error = MagicMock(side_effect=HTTPException(status_code=401))
    sys.modules["auth_middleware"] = _auth_stub

# Stub onboarding.doctor to avoid psutil/hardware probing at collection time.
if "onboarding.doctor" not in sys.modules:
    _doctor_stub = types.ModuleType("onboarding.doctor")
    _doctor_stub.run_doctor = AsyncMock(return_value={"status": "ok"})
    sys.modules["onboarding.doctor"] = _doctor_stub

# Import the real router (with auth deps in place after the fix).
from api.onboarding import router as _onboarding_router  # noqa: E402

# ── test helpers ──────────────────────────────────────────────────────────────


def _raise_401() -> None:
    """Simulates an unauthenticated request — raises 401 like the real deps would."""
    raise HTTPException(status_code=401, detail="Authentication required")


def _allow_user() -> dict:
    return {"username": "test-admin", "role": "admin"}


def _allow_admin() -> bool:
    return True


def _unauthenticated_client() -> TestClient:
    """TestClient that overrides both auth deps to reject all requests.

    This is the regression probe: if a protected route loses its Depends(...)
    declaration, the override never fires and the endpoint returns 2xx — causing
    the assertion to fail and the regression to be detected.
    """
    app = FastAPI()
    app.include_router(_onboarding_router, prefix="/api/onboarding")
    from auth_middleware import check_admin_permission, get_current_user

    app.dependency_overrides[get_current_user] = _raise_401
    app.dependency_overrides[check_admin_permission] = _raise_401
    return TestClient(app, raise_server_exceptions=False)


def _authenticated_client() -> TestClient:
    """TestClient that overrides both auth deps to allow all requests."""
    app = FastAPI()
    app.include_router(_onboarding_router, prefix="/api/onboarding")
    from auth_middleware import check_admin_permission, get_current_user

    app.dependency_overrides[get_current_user] = _allow_user
    app.dependency_overrides[check_admin_permission] = _allow_admin
    return TestClient(app, raise_server_exceptions=False)


# ── GH #6568 regression: privileged endpoints must enforce auth ───────────────


class TestOnboardingUnauthenticatedReturns401:
    """Each auth-gated endpoint must return 401 for unauthenticated requests.

    Uses dependency_overrides as a structural probe: the override fires only
    when the route actually declares the dependency. A missing Depends(...)
    means the override is silently skipped, the endpoint runs its business
    logic, and returns a status other than 401 — failing the assertion.
    """

    def test_presets_requires_authentication(self):
        """GET /api/onboarding/presets → 401 without credentials (GH #6568)."""
        resp = _unauthenticated_client().get("/api/onboarding/presets")
        assert resp.status_code == 401, (
            f"GET /api/onboarding/presets returned HTTP {resp.status_code}; expected 401. "
            "GH #6568 regression: ensure Depends(get_current_user) is on this route."
        )

    def test_doctor_requires_authentication(self):
        """GET /api/onboarding/doctor → 401 without credentials (GH #6568)."""
        resp = _unauthenticated_client().get("/api/onboarding/doctor")
        assert resp.status_code == 401, (
            f"GET /api/onboarding/doctor returned HTTP {resp.status_code}; expected 401. "
            "GH #6568 regression: ensure Depends(get_current_user) is on this route."
        )

    def test_apply_requires_admin_permission(self):
        """POST /api/onboarding/apply → 401 without credentials (GH #6568)."""
        resp = _unauthenticated_client().post(
            "/api/onboarding/apply",
            json={"preset_name": "chat-simple", "overrides": {}},
        )
        assert resp.status_code == 401, (
            f"POST /api/onboarding/apply returned HTTP {resp.status_code}; expected 401. "
            "GH #6568 regression: ensure Depends(check_admin_permission) is on this route."
        )


class TestOnboardingStatusIsIntentionallyOpen:
    """/status must remain unauthenticated — pre-login probe for the frontend router guard.

    The fix (#6568) intentionally left /status open. These tests ensure it
    stays accessible without credentials and that no future change accidentally
    auth-gates it, which would break the frontend before-login flow.
    """

    def test_status_accessible_without_credentials(self):
        """GET /api/onboarding/status → 200 without authentication (GH #6568).

        NOTE: /status is intentionally unauthenticated. The frontend router
        guard calls this endpoint pre-login to determine whether onboarding is
        needed. Do NOT add auth deps to this route.
        """
        resp = _unauthenticated_client().get("/api/onboarding/status")
        assert resp.status_code == 200, (
            f"GET /api/onboarding/status returned HTTP {resp.status_code}; expected 200. "
            "Do NOT add auth to /status — it is intentionally open (GH #6568)."
        )


class TestOnboardingAuthenticatedHappyPath:
    """Auth-gated endpoints must reach business logic when valid credentials are provided."""

    def test_presets_succeeds_when_authenticated(self):
        """GET /api/onboarding/presets → 200 with valid credentials."""
        from unittest.mock import patch

        with patch("onboarding.presets.get_all_presets", return_value=[]):
            resp = _authenticated_client().get("/api/onboarding/presets")
        assert resp.status_code == 200

    def test_apply_reaches_business_logic_when_authenticated(self):
        """POST /api/onboarding/apply → business logic runs (404 for unknown preset)."""
        from unittest.mock import patch

        with patch("onboarding.presets.get_preset", return_value=None):
            resp = _authenticated_client().post(
                "/api/onboarding/apply",
                json={"preset_name": "no-such-preset", "overrides": {}},
            )
        assert resp.status_code == 404
