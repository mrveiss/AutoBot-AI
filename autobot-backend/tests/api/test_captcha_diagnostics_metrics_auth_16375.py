# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No route in captcha/diagnostics/metrics serves an unauthenticated caller (#16375).

All three routers were reachable anonymously. Each now depends on
``get_current_user`` at router level; metrics' two monitoring-control routes
also depend on ``check_admin_permission``. Runtime negative control,
complementing ``config_router_auth_coverage_test.py``'s source-level sweep
(which only checks that SOME gate is declared, never that it actually
refuses a request) -- pattern from ``test_skills_auth_16368.py``.

These tests judge that with the REAL dependencies, the same way.
"""

from types import SimpleNamespace
from typing import Dict, Tuple

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import api.captcha as captcha_api
import api.diagnostics as diagnostics_api
import api.metrics as metrics_api
from autobot_shared.api_routing.router_routes import effective_routes

_ADMIN, _USER = "admin", "user"

#: The per-route policy, pinned. A route added to any of the three routers
#: fails ``test_the_policy_table_covers_every_route`` until it is classified here.
_POLICY: Dict[Tuple[str, str], str] = {
    ("POST", "/api/captcha/{captcha_id}/resolve"): _USER,
    ("POST", "/api/captcha/{captcha_id}/skip"): _USER,
    ("GET", "/api/captcha/pending"): _USER,
    ("POST", "/api/diagnostics/analyze-failure"): _USER,
    ("GET", "/api/diagnostics/analyze-failure"): _USER,
    ("GET", "/api/metrics/workflow/{workflow_id}"): _USER,
    ("GET", "/api/metrics/performance/summary"): _USER,
    ("GET", "/api/metrics/system/current"): _USER,
    ("GET", "/api/metrics/system/history"): _USER,
    ("GET", "/api/metrics/system/summary"): _USER,
    ("GET", "/api/metrics/export/workflow"): _USER,
    ("GET", "/api/metrics/export/system"): _USER,
    ("POST", "/api/metrics/system/monitoring/start"): _ADMIN,
    ("POST", "/api/metrics/system/monitoring/stop"): _ADMIN,
    ("GET", "/api/metrics/dashboard"): _USER,
}
_PATH_VALUES = {"{captcha_id}": "demo", "{workflow_id}": "demo"}
#: analyze-failure's GET twin requires this query param before it can even
#: reach the auth dependency's result -- present on every call, harmless elsewhere.
_QUERY = {"task_id": "demo"}
_NON_ADMIN = {"username": "viewer", "role": "user"}

#: Matches app_factory.py's ``app.include_router(router, prefix=f"/api{registry_prefix}")``.
#: captcha.py and diagnostics.py already bake their own ``/captcha``/``/diagnostics``
#: prefix into the router (registry_prefix=""); metrics.py has none, so the
#: registry supplies ``/metrics`` (monitoring_routers.py).
_MOUNTS = (
    ("/api", captcha_api.router),
    ("/api", diagnostics_api.router),
    ("/api/metrics", metrics_api.router),
)


def _app() -> FastAPI:
    app = FastAPI()
    for prefix, router in _MOUNTS:
        app.include_router(router, prefix=prefix)
    return app


def _routes() -> set:
    """Served ``(method, path)`` pairs, read per router rather than off the app (#15093)."""
    found = set()
    for prefix, router in _MOUNTS:
        for mounted in effective_routes(router):
            assert mounted.prefix_complete, mounted.path
            if isinstance(mounted.route, APIRoute):
                found.update((method, prefix + mounted.path) for method in mounted.methods)
    return found


def _call(test_client: TestClient, method: str, path: str):
    url = path
    for placeholder, value in _PATH_VALUES.items():
        url = url.replace(placeholder, value)
    return test_client.request(method, url, params=_QUERY, json={} if method == "POST" else None)


@pytest.fixture
def client(real_auth_middleware, monkeypatch):
    """A client whose gate is the production code; ``identity.user`` is what it sees."""
    identity = SimpleNamespace(user=None)

    async def _no_token(_request):
        return None

    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: identity.user,
        _extract_user_from_run_jwt=_no_token,
        _extract_user_from_device_jwt=_no_token,
    )
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    app = _app()
    for module in (captcha_api, diagnostics_api, metrics_api):
        app.dependency_overrides[module.get_current_user] = real_auth_middleware.get_current_user
    app.dependency_overrides[metrics_api.check_admin_permission] = real_auth_middleware.check_admin_permission
    return TestClient(app), identity


def test_the_policy_table_covers_every_route() -> None:
    """A route added to any of the three routers must be classified here, admin or user, before it ships."""
    assert _routes() == set(_POLICY)


@pytest.mark.parametrize(("method", "path"), sorted(_POLICY))
def test_an_anonymous_caller_is_refused(client, method: str, path: str) -> None:
    test_client, _ = client

    assert _call(test_client, method, path).status_code == 401


_ADMIN_ROUTES = sorted(key for key, level in _POLICY.items() if level == _ADMIN)


@pytest.mark.parametrize(("method", "path"), _ADMIN_ROUTES)
def test_a_non_admin_is_refused_where_admin_is_required(client, method: str, path: str) -> None:
    test_client, identity = client
    identity.user = dict(_NON_ADMIN)

    assert _call(test_client, method, path).status_code == 403


def test_a_non_admin_still_reaches_a_user_route(client) -> None:
    """The control: the 401s and 403s above come from the gate, not from a broken override."""
    test_client, identity = client
    identity.user = dict(_NON_ADMIN)

    response = _call(test_client, "GET", "/api/metrics/dashboard")

    assert response.status_code == 200, response.text
