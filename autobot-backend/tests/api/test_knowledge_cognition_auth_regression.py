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

GH #15796: the ``auth_middleware`` stub below used to be a bare
``sys.modules["auth_middleware"] = ...`` assignment, installed once at
import time and never removed. That let this module's allow-all
``check_admin_permission`` leak into every test collected afterward in the
same pytest process, and made the winner (this stub vs. whatever else was
already there) depend on collection order. The stub is now installed and
reverted inside a ``try/finally`` scoped tightly around the one import that
needs it -- ``api.knowledge_cognition``'s own module-level
``from auth_middleware import check_admin_permission``. Every test below
keys ``dependency_overrides`` off ``api.knowledge_cognition.check_admin_permission``
(not a fresh ``from auth_middleware import ...``), because that name is
bound once, at router-import time, and stays the same object regardless of
what ``auth_middleware`` becomes afterward.
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
    """Import-time stub: approves all requests so the router import below can
    inspect and register ``Depends(check_admin_permission)``. Never consulted
    at test time -- every test overrides it via ``dependency_overrides``.
    """
    return True


def _build_auth_middleware_stub() -> types.ModuleType:
    """A fresh, FastAPI-inspectable ``auth_middleware`` stub module."""
    stub = types.ModuleType("auth_middleware")
    stub.check_admin_permission = _stub_check_admin_permission
    stub.get_auth_middleware = MagicMock()
    stub.raise_auth_error = MagicMock(side_effect=HTTPException(status_code=401))
    return stub


# Save whatever (if anything) already occupies the canonical name so it can
# be put back exactly as found -- unconditionally, so the outcome never
# depends on whether some other module imported ``auth_middleware`` first.
_prior_auth_middleware = sys.modules.get("auth_middleware")
sys.modules["auth_middleware"] = _build_auth_middleware_stub()

try:
    # ── import the real cognition router (fix applied -- now wired via Depends) ──
    from api.knowledge_cognition import check_admin_permission as _bound_admin_check  # noqa: E402
    from api.knowledge_cognition import router as _cognition_router
finally:
    # The router captured `check_admin_permission` as a Python object inside its
    # Depends(...), so reverting `auth_middleware` cannot un-bind it -- and that
    # is exactly why restoring `auth_middleware` alone is NOT enough.
    #
    # `api.knowledge_cognition` is a shared singleton: `initialization/
    # router_registry/core_routers.py:55` imports the same module to build the
    # real application. Leaving it cached here would hand every later importer
    # -- including the real app inside the same pytest process -- a router whose
    # admin dependency is this file's allow-all stub. That is the original
    # defect moved one level down, and strictly worse: a leak into
    # `sys.modules["auth_middleware"]` only affects code that imports that name
    # afterwards, while a leak into the cached router affects the app itself.
    #
    # Dropping the module entry forces the next importer to re-import against
    # the real `auth_middleware`. The reference bound above stays valid for this
    # file's own TestClient, which is the only thing that should see the stub.
    for _cached in ("api.knowledge_cognition",):
        sys.modules.pop(_cached, None)
    if _prior_auth_middleware is None:
        sys.modules.pop("auth_middleware", None)
    else:
        sys.modules["auth_middleware"] = _prior_auth_middleware

# ── test helpers ──────────────────────────────────────────────────────────────


def _raise_401() -> None:
    """Simulates a rejected (unauthenticated/non-admin) caller -- 401."""
    raise HTTPException(status_code=401, detail="Authentication required")


def _allow_admin() -> bool:
    return True


def _make_client(*, allow: bool) -> TestClient:
    """TestClient with check_admin_permission overridden to allow or reject.

    Keyed off ``_bound_admin_check`` -- the object captured at router-import
    time -- rather than any later import (GH #15796). Both restorations above
    make a fresh import return a *different* function: ``auth_middleware`` is
    reverted, and ``api.knowledge_cognition`` is evicted so the real app
    re-imports it cleanly. ``dependency_overrides`` is keyed by object identity,
    so only the captured reference matches what the router actually bound.
    """
    app = FastAPI()
    app.include_router(_cognition_router, prefix="/api/knowledge")
    check_admin_permission = _bound_admin_check

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


class TestAuthMiddlewareStubDoesNotLeak:
    """GH #15796: the router-import stub must not outlive the import it existed for."""

    def test_the_shared_router_module_is_not_left_cached_with_the_stub(self):
        """The stub must not survive in ``sys.modules["api.knowledge_cognition"]``.

        That module is a singleton: ``initialization/router_registry/
        core_routers.py:55`` imports it to build the real application. Leaving it
        cached here hands every later importer -- the real app included -- a
        router whose admin dependency is this file's allow-all stub. Restoring
        ``auth_middleware`` alone does not undo that, because the router bound
        the function object, not the module name.
        """
        cached = sys.modules.get("api.knowledge_cognition")
        if cached is not None:
            assert cached.check_admin_permission is not _stub_check_admin_permission, (
                "api.knowledge_cognition is cached with the allow-all stub bound -- "
                "the real app would import this router with no admin check"
            )

    def test_auth_middleware_restored_after_module_import(self):
        """``auth_middleware`` must not still be this module's stub.

        The module-level ``try/finally`` above installed
        ``_stub_check_admin_permission`` only for the duration of the
        ``api.knowledge_cognition`` import and reverted it immediately
        afterward -- before any test in this file (including this one) runs.
        Importing ``auth_middleware`` fresh here must resolve to whatever was
        there before this test module existed, never to this file's stub.
        """
        import auth_middleware as _reimported

        assert _reimported.check_admin_permission is not _stub_check_admin_permission, (
            "auth_middleware.check_admin_permission is still this test module's "
            "import-time stub -- the stub's scope leaked past the router import "
            "it existed for (GH #15796)."
        )
