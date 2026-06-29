# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for POST/GET /api/settings/telemetry (Issue #9035, #10000).

Covers:
  - POST returns 200 with a DB session present
  - POST returns 200 when the optional session is None (defensive guard) — #10000
  - Audit trail is called when session is present, skipped when None
  - GET returns 200 and correct field values

The conftest.py auth_middleware stub uses __getattr__ = lambda: MagicMock(), which
creates a new MagicMock object on every attribute access.  FastAPI stores the specific
object that was passed to Depends() at route-registration time, so overrides keyed on
a fresh import of the same attribute name miss.  We resolve this by extracting the
registered dependency objects directly from the route via _registered_deps() and keying
dependency_overrides on those exact objects.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.settings import router
from api.user_management.dependencies import get_optional_db_session

# ---------------------------------------------------------------------------
# Session stub callables
# ---------------------------------------------------------------------------


async def _session_present():
    """Stub for get_optional_db_session: yields a fake session object."""
    yield MagicMock()


async def _session_absent():
    """Stub for get_optional_db_session: yields None (defensive-guard path)."""
    yield None


# ---------------------------------------------------------------------------
# Helper: extract registered dependency function objects from the router
# ---------------------------------------------------------------------------


def _registered_deps(method: str, path_suffix: str) -> dict:
    """Return {param_name: dependency_fn} for the named route as registered.

    FastAPI stores the actual callable objects inside Depends().  To key
    dependency_overrides correctly we must use those exact objects, not fresh
    imports of the same name (which may be different MagicMock instances when
    the stub module uses __getattr__).
    """
    for route in router.routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        if method.upper() not in route.methods:
            continue
        if not route.path.endswith(path_suffix):
            continue
        sig = inspect.signature(route.endpoint)
        result = {}
        for name, param in sig.parameters.items():
            default = param.default
            if hasattr(default, "dependency"):
                result[name] = default.dependency
        return result
    raise KeyError(f"Route {method} *{path_suffix} not found in router")


# Cache at module level so we extract once per test session.
_POST_DEPS = _registered_deps("POST", "/telemetry")
_GET_DEPS = _registered_deps("GET", "/telemetry")

# ---------------------------------------------------------------------------
# Shared admin stubs
# ---------------------------------------------------------------------------


def _admin_user() -> dict:
    return {"username": "admin", "role": "admin", "id": "user-1"}


def _allow_admin():
    return None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app(*, with_session: bool = True) -> FastAPI:
    """Minimal FastAPI app that mounts only the settings router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/settings")
    app.dependency_overrides[get_optional_db_session] = _session_present if with_session else _session_absent
    # Override the auth deps using the exact objects captured at registration time.
    if "current_user" in _POST_DEPS:
        app.dependency_overrides[_POST_DEPS["current_user"]] = _admin_user
    if "_" in _POST_DEPS:
        app.dependency_overrides[_POST_DEPS["_"]] = _allow_admin
    if "current_user" in _GET_DEPS:
        app.dependency_overrides[_GET_DEPS["current_user"]] = _admin_user
    return app


# ---------------------------------------------------------------------------
# POST /api/settings/telemetry — with Postgres (session present)
# ---------------------------------------------------------------------------


class TestPostTelemetryWithPostgres:
    """POST /api/settings/telemetry when a DB session is available."""

    def test_returns_200_and_persists(self):
        app = _make_app(with_session=True)

        mock_revision_svc = MagicMock()
        mock_revision_svc.create_revision = AsyncMock()
        fake_cfg = {"telemetry": {"enabled": True, "anonymous_usage_stats": True, "first_run_prompt_shown": False}}

        with (
            patch("api.settings.ConfigService.get_full_config", return_value=dict(fake_cfg)),
            patch("api.settings.ConfigService.save_full_config", return_value={"status": "ok"}),
            patch("api.settings.ConfigService.clear_cache"),
            patch("api.settings.ConfigRevisionService", return_value=mock_revision_svc),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/settings/telemetry",
                json={"enabled": False, "anonymous_usage_stats": False, "first_run_prompt_shown": True},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["first_run_prompt_shown"] is True

    def test_audit_trail_called_when_session_present(self):
        """create_revision IS called when a DB session is available."""
        app = _make_app(with_session=True)

        mock_revision_svc = MagicMock()
        mock_revision_svc.create_revision = AsyncMock()
        fake_cfg = {"telemetry": {"enabled": True, "anonymous_usage_stats": True, "first_run_prompt_shown": False}}

        with (
            patch("api.settings.ConfigService.get_full_config", return_value=dict(fake_cfg)),
            patch("api.settings.ConfigService.save_full_config", return_value={"status": "ok"}),
            patch("api.settings.ConfigService.clear_cache"),
            patch("api.settings.ConfigRevisionService", return_value=mock_revision_svc),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/settings/telemetry",
                json={"enabled": True, "anonymous_usage_stats": True, "first_run_prompt_shown": True},
            )

        assert resp.status_code == 200
        mock_revision_svc.create_revision.assert_awaited_once()


# ---------------------------------------------------------------------------
# POST /api/settings/telemetry — optional session is None (defensive) — #10000
# ---------------------------------------------------------------------------


class TestPostTelemetryNoSession:
    """When get_optional_db_session yields None the endpoint must still save.

    The endpoint saves the config and returns 200 without touching the DB,
    guarding its audit-trail write with ``if session is not None`` (#10000).
    """

    def test_returns_200_without_postgres(self):
        """POST /api/settings/telemetry succeeds with session=None."""
        app = _make_app(with_session=False)

        fake_cfg = {"telemetry": {"enabled": True, "anonymous_usage_stats": True, "first_run_prompt_shown": False}}

        with (
            patch("api.settings.ConfigService.get_full_config", return_value=dict(fake_cfg)),
            patch("api.settings.ConfigService.save_full_config", return_value={"status": "ok"}),
            patch("api.settings.ConfigService.clear_cache"),
            patch("api.settings.ConfigRevisionService", return_value=MagicMock()),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/settings/telemetry",
                json={"enabled": True, "anonymous_usage_stats": False, "first_run_prompt_shown": True},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["first_run_prompt_shown"] is True

    def test_audit_skipped_when_no_session(self):
        """ConfigRevisionService.create_revision is NOT called when session is None."""
        app = _make_app(with_session=False)

        mock_revision_svc = MagicMock()
        mock_revision_svc.create_revision = AsyncMock()
        fake_cfg = {"telemetry": {"enabled": True, "anonymous_usage_stats": True, "first_run_prompt_shown": False}}

        with (
            patch("api.settings.ConfigService.get_full_config", return_value=dict(fake_cfg)),
            patch("api.settings.ConfigService.save_full_config", return_value={"status": "ok"}),
            patch("api.settings.ConfigService.clear_cache"),
            patch("api.settings.ConfigRevisionService", return_value=mock_revision_svc),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/settings/telemetry",
                json={"enabled": False, "anonymous_usage_stats": False, "first_run_prompt_shown": True},
            )

        assert resp.status_code == 200
        mock_revision_svc.create_revision.assert_not_awaited()

    def test_config_saved_without_postgres(self):
        """ConfigService.save_full_config is always called regardless of DB availability."""
        app = _make_app(with_session=False)

        save_mock = MagicMock(return_value={"status": "ok"})
        fake_cfg = {"telemetry": {"enabled": True, "anonymous_usage_stats": True, "first_run_prompt_shown": False}}

        with (
            patch("api.settings.ConfigService.get_full_config", return_value=dict(fake_cfg)),
            patch("api.settings.ConfigService.save_full_config", save_mock),
            patch("api.settings.ConfigService.clear_cache"),
            patch("api.settings.ConfigRevisionService", return_value=MagicMock()),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/settings/telemetry",
                json={"enabled": True, "anonymous_usage_stats": True, "first_run_prompt_shown": True},
            )

        assert resp.status_code == 200
        save_mock.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/settings/telemetry
# ---------------------------------------------------------------------------


class TestGetTelemetry:
    def test_returns_current_telemetry_settings(self):
        """GET /api/settings/telemetry returns config values from ssot_config."""
        app = _make_app()

        class _FakeTelemetry:
            enabled = True
            anonymous_usage_stats = True
            first_run_prompt_shown = False

        class _FakeConfig:
            telemetry = _FakeTelemetry()

        # The handler imports config inside its body from autobot_shared.ssot_config;
        # patch it at the source module.
        with patch("autobot_shared.ssot_config.config", _FakeConfig()):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/settings/telemetry")

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["anonymous_usage_stats"] is True
        assert body["first_run_prompt_shown"] is False
