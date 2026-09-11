# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No route in the skills API serves an unauthenticated caller (#16368).

Every route in both files was reachable anonymously, ``/{name}/execute`` and
the hub ``/install`` included. Both routers now depend on ``get_current_user``
at router level, and every route that changes state, fetches from outside or
executes a skill also depends on ``check_admin_permission``. The sibling
``skills_repos`` and ``skills_governance`` routers had the same gap on their reads,
and are covered here too.

These tests judge that with the REAL dependencies. Under pytest,
``auth_middleware`` is the conftest stub, whose ``get_current_user`` always
returns an admin, so the routers' ``Depends(...)`` captured stub callables.
Each test overrides exactly the objects the two router modules bound -- which
are what their ``Depends`` captured -- with the real functions from
``real_auth_middleware``, and controls only the identity the real code reads.
"""

from types import SimpleNamespace
from typing import Dict, Tuple

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import api.skills as skills_api
import api.skills_governance as governance_api
import api.skills_hub as hub_api
import api.skills_repos as repos_api

_ADMIN, _USER = "admin", "user"

#: The per-route policy, pinned. A route added to either router fails
#: ``test_the_policy_table_covers_every_route`` until it is classified here.
_POLICY: Dict[Tuple[str, str], str] = {
    ("GET", "/api/skills/"): _USER,
    ("GET", "/api/skills/categories"): _USER,
    ("POST", "/api/skills/initialize"): _ADMIN,
    ("GET", "/api/skills/traces"): _ADMIN,
    ("GET", "/api/skills/catalog"): _ADMIN,
    ("POST", "/api/skills/catalog/{name}/install"): _ADMIN,
    ("GET", "/api/skills/bundles"): _USER,
    ("POST", "/api/skills/bundles/{bundle_id}/enable"): _ADMIN,
    ("GET", "/api/skills/{name}"): _USER,
    ("POST", "/api/skills/{name}/enable"): _ADMIN,
    ("POST", "/api/skills/{name}/disable"): _ADMIN,
    ("PUT", "/api/skills/{name}/config"): _ADMIN,
    ("POST", "/api/skills/{name}/execute"): _ADMIN,
    ("GET", "/api/skills/{name}/health"): _USER,
    ("GET", "/api/skills/{name}/actions"): _USER,
    ("GET", "/api/skills/{name}/metrics"): _USER,
    ("POST", "/api/skills/{name}/feedback"): _USER,
    ("GET", "/api/skills/{name}/suggestions"): _USER,
    ("GET", "/api/skills/hub/search"): _USER,
    ("POST", "/api/skills/hub/install"): _ADMIN,
    ("DELETE", "/api/skills/hub/install/{skill_id}"): _ADMIN,
    ("GET", "/api/skills/hub/installed"): _USER,
    ("GET", "/api/skills/hub/updates"): _USER,
    ("GET", "/api/skills/repos"): _USER,
    ("GET", "/api/skills/repos/"): _USER,
    ("POST", "/api/skills/repos/"): _ADMIN,
    ("POST", "/api/skills/repos/{repo_id}/sync"): _ADMIN,
    ("GET", "/api/skills/repos/{repo_id}/browse"): _USER,
    ("POST", "/api/skills/governance/gaps"): _ADMIN,
    ("GET", "/api/skills/governance/drafts"): _ADMIN,
    ("POST", "/api/skills/governance/drafts/{skill_id}/test"): _ADMIN,
    ("POST", "/api/skills/governance/drafts/{skill_id}/promote"): _ADMIN,
    ("GET", "/api/skills/governance/approvals"): _ADMIN,
    ("POST", "/api/skills/governance/approvals/{approval_id}"): _ADMIN,
    ("GET", "/api/skills/governance/"): _ADMIN,
    ("PUT", "/api/skills/governance/"): _ADMIN,
}
_PATH_VALUES = {
    "{name}": "demo",
    "{bundle_id}": "research",
    "{skill_id}": "demo",
    "{repo_id}": "demo",
    "{approval_id}": "demo",
}
_NON_ADMIN = {"username": "viewer", "role": "user"}


def _app() -> FastAPI:
    """Mounted as the registry mounts them: sub-routers first, then the base router's ``/{name}``."""
    app = FastAPI()
    app.include_router(hub_api.router, prefix="/api/skills/hub")
    app.include_router(repos_api.router, prefix="/api/skills/repos")
    app.include_router(governance_api.router, prefix="/api/skills/governance")
    app.include_router(skills_api.router, prefix="/api/skills")
    return app


def _routes(app: FastAPI) -> set:
    return {(method, route.path) for route in app.routes if isinstance(route, APIRoute) for method in route.methods}


def _call(test_client: TestClient, method: str, path: str):
    url = path
    for placeholder, value in _PATH_VALUES.items():
        url = url.replace(placeholder, value)
    return test_client.request(method, url, json={} if method in ("POST", "PUT") else None)


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
    for module in (skills_api, hub_api, repos_api, governance_api):
        app.dependency_overrides[module.get_current_user] = real_auth_middleware.get_current_user
        app.dependency_overrides[module.check_admin_permission] = real_auth_middleware.check_admin_permission
    return TestClient(app), identity


def test_the_policy_table_covers_every_route() -> None:
    """A route added to either router must be classified here, admin or user, before it ships."""
    assert _routes(_app()) == set(_POLICY)


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

    response = _call(test_client, "GET", "/api/skills/bundles")

    assert response.status_code == 200, response.text
