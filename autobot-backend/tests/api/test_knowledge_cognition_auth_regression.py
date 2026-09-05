# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for GH #15759 -- cognition-store seed's admin check never ran.

Linked issue: https://github.com/mrveiss/AutoBot-AI/issues/15759

Bug: ``_user=check_admin_permission`` assigned the dependency *callable itself*
as the parameter's default value -- missing ``Depends(...)``. FastAPI never
invoked ``check_admin_permission``; it was not part of the route's Dependant
tree at all, so ``POST /cognition-store/seed`` ran for every caller regardless
of role, despite naming the check in its signature.

Fix applied: ``_user: bool = Depends(check_admin_permission)``.

Regression guarantee: if ``Depends(...)`` is ever removed again,
``dependency_overrides`` has nothing to hook, the endpoint runs
unconditionally, and the expected 401 in
``test_seed_returns_401_without_admin`` is never returned.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

# ── stub auth_middleware with a proper FastAPI-compatible function ────────────
# FastAPI inspects dependency signatures via inspect.signature(); MagicMock has
# a non-inspectable signature that raises 422. Use a real function instead.


def _stub_check_admin_permission(request: Request) -> bool:
    """Default stub: approves all requests (overridden per-test via dependency_overrides)."""
    return True


if "auth_middleware" not in sys.modules:
    _auth_stub = types.ModuleType("auth_middleware")
    _auth_stub.check_admin_permission = _stub_check_admin_permission
    _auth_stub.get_auth_middleware = MagicMock()
    _auth_stub.raise_auth_error = MagicMock(side_effect=HTTPException(status_code=401))
    sys.modules["auth_middleware"] = _auth_stub

# ── import the real cognition router (fix applied -- now wired via Depends) ──
from api.knowledge_cognition import router as _cognition_router  # noqa: E402

# ── test helpers ──────────────────────────────────────────────────────────────


def _raise_401() -> None:
    """Simulates a rejected (unauthenticated/non-admin) caller -- 401."""
    raise HTTPException(status_code=401, detail="Authentication required")


def _allow_admin() -> bool:
    return True


def _make_client(*, allow: bool) -> TestClient:
    """TestClient with check_admin_permission overridden to allow or reject."""
    app = FastAPI()
    app.include_router(_cognition_router, prefix="/api/knowledge")
    from auth_middleware import check_admin_permission

    app.dependency_overrides[check_admin_permission] = _allow_admin if allow else _raise_401
    return TestClient(app, raise_server_exceptions=False)


def _mock_seeder() -> AsyncMock:
    """AsyncMock seeder whose seed_from_manifest resolves to a real int.

    A bare AsyncMock() return would resolve `count` to a MagicMock, and the
    handler's `%d` log formatting would raise on that -- so the count is
    pinned to an int explicitly.
    """
    seeder = AsyncMock()
    seeder.seed_from_manifest = AsyncMock(return_value=3)
    return seeder


class TestCognitionSeedAuthEnforcement:
    """POST /cognition-store/seed must reject a non-admin caller -- GH #15759."""

    def test_seed_returns_401_without_admin(self):
        """A non-admin caller must be rejected.

        Before the fix, `_user=check_admin_permission` was a bare default, so
        FastAPI never called it and `dependency_overrides` had nothing to
        hook -- the endpoint ran unconditionally, returning 200/404 instead of
        401. This assertion only passes once the gate is wired via
        Depends(...).
        """
        client = _make_client(allow=False)
        resp = client.post(
            "/api/knowledge/cognition-store/seed",
            json={"manifest_path": "cognition_seed.yaml"},
        )
        assert resp.status_code == 401, (
            f"POST /cognition-store/seed returned HTTP {resp.status_code}; expected 401. "
            "Regression (GH #15759): add Depends(check_admin_permission) to this route."
        )


class TestCognitionSeedAuthenticatedSuccess:
    """The seed handler must still run to completion for an admin caller."""

    def test_seed_reaches_handler_when_admin(self):
        """Auth passes -> business logic executes -> background seed scheduled."""
        with (
            patch("api.knowledge_cognition.os.path.isfile", return_value=True),
            patch(
                "api.knowledge_cognition.get_cognition_seeder",
                new=AsyncMock(return_value=_mock_seeder()),
            ),
        ):
            client = _make_client(allow=True)
            resp = client.post(
                "/api/knowledge/cognition-store/seed",
                json={"manifest_path": "cognition_seed.yaml"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "seeding_started"
