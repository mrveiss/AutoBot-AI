# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: task ``status/{task_id}`` and ``clear-stuck`` routes carry an auth gate (#18718).

Walks the real routers' ``.routes`` (``dependant.dependencies`` already merges
router-level and route-level dependencies). Explicit module list, no tree scan.
"""

import importlib
import re

import pytest
from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute

from auth_middleware import check_admin_permission, get_current_user

ROUTER_MODULES = [
    "api.analytics",
    "api.analytics_bug_prediction",
    "api.code_intelligence",
    "api.codebase_analytics.endpoints.dependencies",
    "api.codebase_analytics.endpoints.duplicates",
    "api.codebase_analytics.endpoints.import_tree",
    "api.codebase_analytics.endpoints.indexing",
    "api.codebase_analytics.endpoints.pattern_analysis",
]
_TASK_PATH = re.compile(r"/status/\{task_id\}$|/clear-stuck$")
_GATES = {get_current_user, check_admin_permission}


def _task_routes(router):
    return [r for r in router.routes if isinstance(r, APIRoute) and _TASK_PATH.search(r.path)]


def _is_gated(route) -> bool:
    return any(d.call in _GATES for d in route.dependant.dependencies)


def ungated_task_routes(router) -> list:
    """Return ``METHOD path`` of every status/clear-stuck route lacking a gate."""
    return [f"{sorted(r.methods)[0]} {r.path}" for r in _task_routes(router) if not _is_gated(r)]


def _ungated_paths(module):
    router = importlib.import_module(module).router
    assert _task_routes(router), f"{module}: no status/clear-stuck routes found (matcher drift?)"
    return {r.path for r in _task_routes(router) if not _is_gated(r)}


@pytest.mark.parametrize("module", ROUTER_MODULES)
def test_task_routes_are_gated(module):
    assert _ungated_paths(module) == set()


def test_clear_stuck_gates_are_admin():
    for module in ROUTER_MODULES:
        for r in _task_routes(importlib.import_module(module).router):
            calls = {d.call for d in r.dependant.dependencies}
            if r.path.endswith("/clear-stuck"):
                assert check_admin_permission in calls, f"{module} {r.path}"


def test_planted_control_ungated_route_is_flagged():
    fake = APIRouter()

    @fake.get("/x/status/{task_id}")
    async def _bare(task_id: str):
        return {}

    @fake.post("/x/tasks/clear-stuck", dependencies=[Depends(get_current_user)])
    async def _gated():
        return {}

    assert ungated_task_routes(fake) == ["GET /x/status/{task_id}"]


# --- behaviour ---
# conftest replaces ``auth_middleware`` with a stub, so the gates cannot be exercised
# through the real middleware here. Each caller class is modelled by overriding the
# very callables the routes captured in ``Depends`` -- a route lacking the gate
# ignores the override and runs its handler, which is what these tests detect.

PATTERN = "api.codebase_analytics.endpoints.pattern_analysis"
BUG = "api.analytics_bug_prediction"
INDEXING = "api.codebase_analytics.endpoints.indexing"


def _deny(code):
    from fastapi import HTTPException

    def _dep():
        raise HTTPException(status_code=code)

    return _dep


def _allow(*_a, **_k):
    return {"username": "a", "role": "admin"}


def _client(module, caller):
    """TestClient over ``module``'s router; ``caller`` is anonymous, user or admin."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    mod = importlib.import_module(module)
    app.include_router(mod.router)
    if caller == "anonymous":
        app.dependency_overrides[get_current_user] = _deny(401)
        app.dependency_overrides[check_admin_permission] = _deny(401)
    elif caller == "user":
        app.dependency_overrides[get_current_user] = _allow
        app.dependency_overrides[check_admin_permission] = _deny(403)
    else:
        app.dependency_overrides[get_current_user] = _allow
        app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


@pytest.mark.parametrize("caller,code", [("anonymous", 401), ("user", 403)])
def test_pattern_task_revoke_requires_admin_and_does_not_revoke(caller, code):
    from unittest.mock import patch

    client = _client(PATTERN, caller)
    with patch("celery_app.celery_app.control.revoke") as revoke:
        assert client.delete("/patterns/task/x").status_code == code
    revoke.assert_not_called()


def test_pattern_task_revoke_admin_revokes():
    from unittest.mock import patch

    client = _client(PATTERN, "admin")
    with patch("celery_app.celery_app.control.revoke") as revoke:
        assert client.delete("/patterns/task/x").status_code == 200
    revoke.assert_called_once_with("x", terminate=True)


@pytest.mark.parametrize("path", ["/patterns/result/x", "/patterns/tasks"])
def test_pattern_result_and_list_require_authentication(path):
    assert _client(PATTERN, "anonymous").get(path).status_code == 401


@pytest.mark.parametrize("caller,code", [("anonymous", 401), ("user", 403), ("admin", 200)])
def test_bug_prediction_clear_stuck_gated_and_same_body(caller, code):
    resp = _client(BUG, caller).post("/bug-prediction/tasks/clear-stuck?force=true")
    assert resp.status_code == code
    if code == 200:
        assert resp.json() == {"cleared_count": 0, "message": "Celery handles task recovery automatically"}


def _destructive_routes():
    """Every clear-stuck route plus the destructive pattern/index routes."""
    routes = [
        (m, r)
        for m in ROUTER_MODULES
        for r in _task_routes(importlib.import_module(m).router)
        if r.path.endswith("/clear-stuck")
    ]
    for module, path in [(PATTERN, "/patterns/tasks/clear-all"), (INDEXING, "/index/cancel")]:
        found = [r for r in importlib.import_module(module).router.routes if getattr(r, "path", None) == path]
        assert found, f"{module} {path}: route not found"
        routes += [(module, r) for r in found]
    return routes


def test_every_destructive_route_refuses_the_service_principal_before_the_admin_check():
    """Destructive task routes are human-admin-only (owner, 2026-10-18; #18688)."""
    from security.human_admin import refuse_service_principal

    for module, r in _destructive_routes():
        calls = [d.call for d in r.dependant.dependencies]
        assert refuse_service_principal in calls, (module, r.path)
        assert calls.index(refuse_service_principal) < calls.index(check_admin_permission), (module, r.path)


@pytest.fixture
def internal_key(monkeypatch):
    import security.human_admin as human_admin

    monkeypatch.setattr(human_admin.auth_middleware, "verify_internal_api_key", lambda key: key == "svc-key")
    return {"X-Internal-API-Key": "svc-key"}


def test_the_internal_key_cannot_revoke_a_pattern_task(internal_key):
    from unittest.mock import patch

    client = _client(PATTERN, "admin")  # the key's principal is admin; the refusal must still win
    with patch("celery_app.celery_app.control.revoke") as revoke:
        assert client.delete("/patterns/task/x", headers=internal_key).status_code == 403
    revoke.assert_not_called()


def test_the_internal_key_cannot_clear_stuck_tasks(internal_key):
    resp = _client(BUG, "admin").post("/bug-prediction/tasks/clear-stuck?force=true", headers=internal_key)
    assert resp.status_code == 403


# --- the REAL gates (#18718) ---
# Fresh copies of the routers execute with the real ``auth_middleware`` bound, so the
# routes' own ``Depends`` is judged; only the identity the real gate reads is faked.

_KEY = "svc-key"
_ADMIN = {"username": "root", "role": "admin"}
_USER = {"username": "viewer", "role": "user"}
_ENDPOINTS = "api.codebase_analytics.endpoints"


def _exec_fresh(monkeypatch, name, relpath):
    import sys
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    spec = spec_from_file_location(name, Path(__file__).parent / relpath)
    module = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def real_gate(monkeypatch):
    """Fresh routers bound to the real gate; ``state.user`` is the identity it sees."""
    import sys
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tests.conftest import load_real_auth_middleware

    state = SimpleNamespace(user=None)
    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: state.user,
        _extract_user_from_run_jwt=AsyncMock(return_value=None),
        _extract_user_from_device_jwt=AsyncMock(return_value=None),
    )
    real = load_real_auth_middleware()
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(real, "verify_internal_api_key", lambda provided: provided == _KEY)
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    # HUMAN_ADMIN_DEPENDENCIES binds the gate when security.human_admin loads (the stub under
    # pytest), so the shared list is rebuilt fresh against the real gate before the routers load.
    _exec_fresh(monkeypatch, "security.human_admin", "../security/human_admin.py")
    _exec_fresh(monkeypatch, "api.codebase_analytics.task_routes", "codebase_analytics/task_routes.py")
    app = FastAPI()
    for mod, rel in [
        ("api.analytics_bug_prediction", "analytics_bug_prediction.py"),
        (f"{_ENDPOINTS}.pattern_analysis", "codebase_analytics/endpoints/pattern_analysis.py"),
        (f"{_ENDPOINTS}.indexing", "codebase_analytics/endpoints/indexing.py"),
    ]:
        module = _exec_fresh(monkeypatch, mod, rel)
        app.include_router(module.router)
        setattr(state, mod.rsplit(".", 1)[-1], module)
    state.client = TestClient(app, raise_server_exceptions=False)
    return state


def _celery(active):
    from unittest.mock import MagicMock, patch

    control = MagicMock()
    control.inspect.return_value.active.return_value = active
    return patch("celery_app.celery_app.control", control), control


_ACTIVE = {"w": [{"id": "t1", "name": "analytics.x"}]}
_KEY_HEADER = {"X-Internal-API-Key": _KEY}
_CALLS = [
    ("post", "/bug-prediction/tasks/clear-stuck?force=true", 200),
    ("delete", "/patterns/task/x", 200),
    ("post", "/patterns/tasks/clear-all", 200),
    ("post", "/index/cancel", 200),
]


def _arm_indexing(real_gate):
    from unittest.mock import MagicMock

    task = MagicMock()
    task.done.return_value = False
    real_gate.indexing._current_indexing_task_id = "job"
    real_gate.indexing._active_tasks["job"] = task
    return task


@pytest.mark.parametrize("method,path,_ok", _CALLS)
@pytest.mark.parametrize("who,headers,code", [("anon", {}, 401), ("user", {}, 403), ("key", _KEY_HEADER, 403)])
def test_real_gate_refuses_and_nothing_is_revoked_or_cancelled(real_gate, method, path, _ok, who, headers, code):
    patcher, control = _celery(_ACTIVE)
    task = _arm_indexing(real_gate)
    real_gate.user = _USER if who == "user" else None
    with patcher:
        assert getattr(real_gate.client, method)(path, headers=headers).status_code == code
    control.revoke.assert_not_called()
    task.cancel.assert_not_called()


@pytest.mark.parametrize("method,path,ok", _CALLS)
def test_real_gate_admits_a_human_admin(real_gate, method, path, ok):
    patcher, control = _celery(_ACTIVE)
    task = _arm_indexing(real_gate)
    real_gate.user = dict(_ADMIN)
    with patcher:
        assert getattr(real_gate.client, method)(path).status_code == ok
    if path.endswith("clear-all"):
        control.revoke.assert_called_once_with("t1", terminate=True)
    if path == "/index/cancel":
        task.cancel.assert_called_once()
