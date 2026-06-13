# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLC API Postgres gate in single_user mode (GH#10010).

In single_user mode ``get_async_session_factory()`` hard-raises.  The
``postgres_required`` dependency and the LLC router-level gate must intercept
the call before the session factory is ever touched, returning a clean
HTTP 503 with a descriptive detail message instead of an unhandled
RuntimeError/500.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

import llc.deps as deps_mod
from llc.deps import postgres_required

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(postgres_enabled: bool) -> MagicMock:
    cfg = MagicMock()
    cfg.postgres_enabled = postgres_enabled
    cfg.mode.value = "single_user" if not postgres_enabled else "single_company"
    return cfg


# Target for patching: postgres_required imports lazily from user_management.config
_PATCH_TARGET = "user_management.config.get_deployment_config"


# ---------------------------------------------------------------------------
# Unit tests for postgres_required()
# ---------------------------------------------------------------------------


def test_postgres_required_passes_when_enabled():
    """postgres_required() is a no-op when Postgres is available."""
    with patch(_PATCH_TARGET, return_value=_make_config(postgres_enabled=True)):
        # Should not raise
        postgres_required()


def test_postgres_required_raises_503_when_disabled():
    """postgres_required() raises HTTP 503 in single_user mode."""
    from fastapi import HTTPException

    with patch(_PATCH_TARGET, return_value=_make_config(postgres_enabled=False)):
        with pytest.raises(HTTPException) as exc_info:
            postgres_required()

    assert exc_info.value.status_code == 503


def test_postgres_required_detail_is_helpful():
    """503 detail message mentions PostgreSQL and single_user mode."""
    from fastapi import HTTPException

    with patch(_PATCH_TARGET, return_value=_make_config(postgres_enabled=False)):
        with pytest.raises(HTTPException) as exc_info:
            postgres_required()

    detail = exc_info.value.detail
    assert "PostgreSQL" in detail or "postgres" in detail.lower()
    assert "single_user" in detail


def test_postgres_required_config_error_is_silent():
    """If get_deployment_config() raises an unexpected error, postgres_required
    passes silently and lets the session factory surface the real error."""
    with patch(_PATCH_TARGET, side_effect=RuntimeError("config broken")):
        # Should NOT raise HTTPException — falls through to let factory decide
        postgres_required()


# ---------------------------------------------------------------------------
# Test get_session dependency wiring
# ---------------------------------------------------------------------------


def test_get_session_has_postgres_required_dependency():
    """get_session() must declare postgres_required as a Depends() parameter
    so the gate runs before the session factory is touched (#10010)."""
    sig = inspect.signature(deps_mod.get_session)
    dep_params = [p for p in sig.parameters.values() if hasattr(p.default, "dependency")]
    assert any(
        p.default.dependency is postgres_required for p in dep_params
    ), "postgres_required must be a Depends() on get_session"


# ---------------------------------------------------------------------------
# Integration: router-level gate returns 503
# ---------------------------------------------------------------------------


def test_llc_router_gate_returns_503_via_http():
    """A router configured with dependencies=[Depends(postgres_required)]
    returns 503 when Postgres is disabled."""
    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    test_router = APIRouter(dependencies=[Depends(postgres_required)])

    @test_router.get("/resource")
    async def resource() -> dict:
        return {"ok": True}

    app.include_router(test_router)

    with patch(_PATCH_TARGET, return_value=_make_config(postgres_enabled=False)):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/resource")

    assert response.status_code == 503
    assert "single_user" in response.json().get("detail", "")


def test_llc_router_gate_passes_when_postgres_enabled():
    """Router gate is transparent when Postgres is available."""
    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    test_router = APIRouter(dependencies=[Depends(postgres_required)])

    @test_router.get("/resource")
    async def resource() -> dict:
        return {"ok": True}

    app.include_router(test_router)

    with patch(_PATCH_TARGET, return_value=_make_config(postgres_enabled=True)):
        client = TestClient(app)
        response = client.get("/resource")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
