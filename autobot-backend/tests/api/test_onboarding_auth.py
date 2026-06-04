# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression tests for #6568 — /api/onboarding auth gating, and #6577 — Redis
transaction atomicity.

Before the fix (#6568), all four onboarding endpoints (presets, doctor, apply,
status) were reachable without authentication. ``/apply`` in particular performs
privileged operations: enables agents, activates skills, persists config.

The fix:
  - GET  /onboarding/presets → requires authenticated user
  - GET  /onboarding/doctor  → requires authenticated user
  - POST /onboarding/apply   → requires admin user
  - GET  /onboarding/status  → INTENTIONALLY unauthenticated (bootstrap probe)

Before the fix (#6577), ``apply_preset`` wrote Redis keys individually so a
mid-flight failure could leave a half-applied state. The fix wraps all writes
in a single MULTI/EXEC pipeline (``transaction=True``).
"""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import onboarding as onboarding_api
from auth_middleware import check_admin_permission, get_current_user
from tests.fixtures import make_async_redis, make_redis_pipeline


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


def _make_mock_pipe():
    """Return a canonical pipeline mock that records set() calls and awaits execute() (#7280)."""
    return make_redis_pipeline(execute_returns=[True])


def _make_mock_redis(pipe):
    """Return a canonical Redis mock whose pipeline() returns *pipe* (#7280)."""
    return make_async_redis(pipeline=pipe)


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

        pipe = _make_mock_pipe()
        mock_redis = _make_mock_redis(pipe)

        with (
            patch("api.onboarding.get_preset", return_value={"agents": [], "skills": []}),
            patch("api.onboarding._activate_skills", new=AsyncMock(return_value=[])),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
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


# ---------------------------------------------------------------------------
# #6577 — Redis transaction atomicity
# ---------------------------------------------------------------------------


class TestApplyPresetTransaction:
    """All Redis writes in ``apply_preset`` must execute inside a single
    MULTI/EXEC pipeline so a partial failure leaves no half-written state."""

    def _app(self) -> FastAPI:
        app = _build_app()
        _grant_admin(app)
        return app

    def test_pipeline_created_with_transaction_true(self):
        """pipeline(transaction=True) must be called — not plain pipeline()."""
        pipe = _make_mock_pipe()
        mock_redis = _make_mock_redis(pipe)
        preset = {
            "agents": ["a1"],
            "skills": [],
            "system_prompt": "Hi",
            "llm_tier": "fast",
        }

        with (
            patch("api.onboarding.get_preset", return_value=preset),
            patch("api.onboarding._activate_skills", new=AsyncMock(return_value=[])),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
        ):
            resp = TestClient(self._app()).post("/api/onboarding/apply", json={"preset_name": "starter"})

        assert resp.status_code == 200
        mock_redis.pipeline.assert_called_once_with(transaction=True)

    def test_all_keys_queued_before_execute(self):
        """Every expected key is queued via pipe.set() and execute() is called once."""
        pipe = _make_mock_pipe()
        mock_redis = _make_mock_redis(pipe)
        preset = {
            "agents": ["agent-a", "agent-b"],
            "skills": [],
            "system_prompt": "Hello",
            "llm_tier": "balanced",
        }

        with (
            patch("api.onboarding.get_preset", return_value=preset),
            patch("api.onboarding._activate_skills", new=AsyncMock(return_value=[])),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
        ):
            TestClient(self._app()).post("/api/onboarding/apply", json={"preset_name": "starter"})

        # 2 agents + system_prompt + llm_tier + preset_applied + preset_name = 6 keys
        assert pipe.set.call_count == 6
        set_keys = {c.args[0] for c in pipe.set.call_args_list}
        assert set_keys == {
            "agents:enabled:agent-a",
            "agents:enabled:agent-b",
            "onboarding:config:system_prompt",
            "onboarding:config:llm_tier",
            "onboarding:preset_applied",
            "onboarding:preset_name",
        }
        pipe.execute.assert_awaited_once()

    def test_redis_transaction_failure_rolls_back_skills(self):
        """If the Redis EXEC raises, in-memory skill state is restored and a 500 is returned."""
        pipe = _make_mock_pipe()
        pipe.execute = AsyncMock(side_effect=RuntimeError("Redis EXEC failed"))
        mock_redis = _make_mock_redis(pipe)

        # Simulate a skill that was enabled; track rollback calls
        rollback_calls: list[str] = []

        async def _fake_activate(skill_names, rollback_stack):
            rollback_stack.append(("skill_enabled", _FakeManager(rollback_calls), "my-skill", False))
            return ["my-skill"]

        with (
            patch(
                "api.onboarding.get_preset",
                return_value={"agents": [], "skills": ["my-skill"]},
            ),
            patch("api.onboarding._activate_skills", side_effect=_fake_activate),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
        ):
            resp = TestClient(self._app()).post("/api/onboarding/apply", json={"preset_name": "starter"})

        assert resp.status_code == 500
        # Skill rollback was triggered
        assert "my-skill" in rollback_calls

    def test_no_redis_writes_on_transaction_failure(self):
        """With a failing pipeline, pipe.execute() is called but raises — no individual
        set() result lands in Redis, demonstrating the all-or-nothing guarantee."""
        pipe = _make_mock_pipe()
        pipe.execute = AsyncMock(side_effect=RuntimeError("EXEC error"))
        mock_redis = _make_mock_redis(pipe)

        with (
            patch(
                "api.onboarding.get_preset",
                return_value={"agents": ["a1"], "skills": []},
            ),
            patch("api.onboarding._activate_skills", new=AsyncMock(return_value=[])),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
        ):
            resp = TestClient(self._app()).post("/api/onboarding/apply", json={"preset_name": "starter"})

        assert resp.status_code == 500
        # set() was called (keys were queued) but execute() raised before any write landed
        assert pipe.set.call_count >= 1
        pipe.execute.assert_awaited_once()


class _FakeManager:
    """Minimal stand-in for SkillManager in rollback tests."""

    def __init__(self, rollback_log: list[str]) -> None:
        self._log = rollback_log

    class _Skill:
        def __init__(self, log: list[str], name: str, initial: bool) -> None:
            self._log = log
            self._name = name
            self.enabled = initial

        def __setattr__(self, attr: str, value: object) -> None:
            object.__setattr__(self, attr, value)
            if attr == "enabled":
                self._log.append(self._name)  # type: ignore[attr-defined]

    @property
    def registry(self):
        return self

    def get(self, name: str):
        return _FakeManager._Skill(self._log, name, True)
