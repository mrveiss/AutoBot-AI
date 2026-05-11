# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression tests for #6568 — /api/onboarding auth gating.

Before the fix, all four onboarding endpoints (presets, doctor, apply, status)
were reachable without authentication. ``/apply`` in particular performs
privileged operations: enables agents, activates skills, persists config.

The fix:
  - GET  /onboarding/presets → requires authenticated user
  - GET  /onboarding/doctor  → requires authenticated user
  - POST /onboarding/apply   → requires admin user
  - GET  /onboarding/status  → INTENTIONALLY unauthenticated (bootstrap probe)

These tests pin the dependency wiring so the gating cannot regress silently.
"""

from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import onboarding as onboarding_api
from auth_middleware import check_admin_permission, get_current_user


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(onboarding_api.router, prefix="/api/onboarding")
    return app


def _grant_user(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "username": "alice",
        "role": "user",
    }


def _grant_admin(app: FastAPI) -> None:
    app.dependency_overrides[check_admin_permission] = lambda: True


def _deny_user(app: FastAPI) -> None:
    def _raise():
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _raise


def _deny_admin(app: FastAPI) -> None:
    def _raise():
        raise HTTPException(status_code=403, detail="Admin permission required")

    app.dependency_overrides[check_admin_permission] = _raise


class TestPresetsAuth:
    def test_unauthenticated_request_rejected(self):
        app = _build_app()
        _deny_user(app)
        resp = TestClient(app).get("/api/onboarding/presets")
        assert resp.status_code == 401

    def test_authenticated_user_can_list_presets(self):
        app = _build_app()
        _grant_user(app)
        with patch("api.onboarding.get_all_presets", return_value=[{"name": "starter"}]):
            resp = TestClient(app).get("/api/onboarding/presets")
        assert resp.status_code == 200
        assert resp.json()["data"] == [{"name": "starter"}]


class TestDoctorAuth:
    def test_unauthenticated_request_rejected(self):
        app = _build_app()
        _deny_user(app)
        resp = TestClient(app).get("/api/onboarding/doctor")
        assert resp.status_code == 401

    def test_authenticated_user_can_run_doctor(self):
        app = _build_app()
        _grant_user(app)

        async def _fake_doctor():
            return {"ok": True}

        with patch("api.onboarding.run_doctor", side_effect=_fake_doctor):
            resp = TestClient(app).get("/api/onboarding/doctor")
        assert resp.status_code == 200
        assert resp.json()["data"] == {"ok": True}


class TestApplyAuth:
    def test_unauthenticated_request_rejected(self):
        app = _build_app()
        _deny_admin(app)
        resp = TestClient(app).post("/api/onboarding/apply", json={"preset_name": "starter"})
        # FastAPI maps the 403 raised by the dep to 403; 401 raise would map to 401.
        assert resp.status_code in (401, 403)

    def test_non_admin_user_cannot_apply(self):
        app = _build_app()
        _deny_admin(app)
        resp = TestClient(app).post("/api/onboarding/apply", json={"preset_name": "starter"})
        assert resp.status_code in (401, 403)

    def test_admin_can_apply_preset(self):
        app = _build_app()
        _grant_admin(app)

        async def _enable_agents(*_a, **_k):
            return []

        async def _activate_skills(*_a, **_k):
            return []

        async def _persist_config(*_a, **_k):
            return {"system_prompt": "applied", "llm_tier": "balanced"}

        with (
            patch("api.onboarding.get_preset", return_value={"agents": [], "skills": []}),
            patch("api.onboarding._enable_agents", side_effect=_enable_agents),
            patch("api.onboarding._activate_skills", side_effect=_activate_skills),
            patch("api.onboarding._persist_config", side_effect=_persist_config),
            patch("autobot_shared.redis_client.get_async_redis_client", return_value=None),
        ):
            resp = TestClient(app).post(
                "/api/onboarding/apply",
                json={"preset_name": "starter"},
            )
        assert resp.status_code == 200


class TestStatusStaysUnauthenticated:
    """``/onboarding/status`` is INTENTIONALLY unauthenticated — frontend router
    guard calls it pre-login to decide whether to redirect to /onboarding.
    Adding auth here would trap new users in a redirect loop (#6452)."""

    def test_no_auth_dependency_attached_to_status_route(self):
        # The route must not have either auth dependency in its dependency list.
        status_route = next(r for r in onboarding_api.router.routes if getattr(r, "path", None) == "/status")
        dep_callables = [d.dependency for d in (status_route.dependencies or [])]
        assert get_current_user not in dep_callables
        assert check_admin_permission not in dep_callables

    def test_status_endpoint_reachable_without_overrides(self):
        app = _build_app()

        # Don't grant auth. Status must still respond.
        async def _no_redis(**_kw):
            return None

        with patch("autobot_shared.redis_client.get_async_redis_client", side_effect=_no_redis):
            resp = TestClient(app).get("/api/onboarding/status")
        assert resp.status_code == 200
        # Fail-open semantics: when Redis is unavailable, return preset_applied=True
        assert resp.json()["preset_applied"] is True


class TestRouteDependenciesPinned:
    """Lock in which dependencies are attached to each route so future edits
    cannot silently drop auth from the privileged endpoints."""

    @staticmethod
    def _dep_callables_for(path: str):
        route = next(r for r in onboarding_api.router.routes if getattr(r, "path", None) == path)
        return [d.dependency for d in (route.dependencies or [])]

    def test_presets_requires_get_current_user(self):
        assert get_current_user in self._dep_callables_for("/presets")

    def test_doctor_requires_get_current_user(self):
        assert get_current_user in self._dep_callables_for("/doctor")

    def test_apply_requires_check_admin_permission(self):
        assert check_admin_permission in self._dep_callables_for("/apply")
