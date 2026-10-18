# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The routes #18722 de-doubled are served at their single-prefix path, and the old
doubled path answers a method-preserving 308 to it (shim removal: #18793)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Match

from api.knowledge_grounding import router as grounding_router
from api.knowledge_ownership import router as ownership_router
from api.system_cache_coordinator import router as coordinator_router
from auth_middleware import check_admin_permission, get_current_user

_SYSTEM = "/api/system"
_KB = "/api/knowledge_base"

#: (method, old doubled path, new single-prefix path), full served paths.
_MOVES = [
    ("GET", f"{_SYSTEM}/api/cache/stats", f"{_SYSTEM}/cache/coordinator/stats"),
    ("POST", f"{_SYSTEM}/api/cache/evict", f"{_SYSTEM}/cache/evict"),
    ("POST", f"{_SYSTEM}/api/cache/clear/lru_memory", f"{_SYSTEM}/cache/clear/lru_memory"),
    ("POST", f"{_KB}/api/knowledge/facts/f1/share", f"{_KB}/facts/f1/share"),
    ("DELETE", f"{_KB}/api/knowledge/facts/f1/share/u2", f"{_KB}/facts/f1/share/u2"),
    ("PUT", f"{_KB}/api/knowledge/facts/f1/visibility", f"{_KB}/facts/f1/visibility"),
    ("GET", f"{_KB}/api/knowledge/facts/mine", f"{_KB}/facts/mine"),
    ("GET", f"{_KB}/api/knowledge/facts/shared-with-me", f"{_KB}/facts/shared-with-me"),
    ("POST", f"{_KB}/api/ground-response", f"{_KB}/ground-response"),
    ("POST", f"{_KB}/api/verify-claim", f"{_KB}/verify-claim"),
    ("GET", f"{_KB}/api/kb-conflicts", f"{_KB}/kb-conflicts"),
    ("POST", f"{_KB}/api/kb-conflicts/c1/resolve", f"{_KB}/kb-conflicts/c1/resolve"),
    ("GET", f"{_KB}/api/kb-stats", f"{_KB}/kb-stats"),
]


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(coordinator_router, prefix=_SYSTEM)
    app.include_router(ownership_router, prefix=_KB)
    app.include_router(grounding_router, prefix=_KB)
    return app


@pytest.fixture
def anonymous(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The same mounts, gated by the REAL dependencies and a caller with no credentials.

    Under pytest ``auth_middleware`` is a conftest stub whose gates admit everyone, so the
    routers captured stub callables; each is overridden with the real function from
    ``load_real_auth_middleware`` (the approach of ``tests/api/test_router_auth_16375.py``), and
    the middleware those read finds no user.
    """
    from tests.conftest import load_real_auth_middleware

    real = load_real_auth_middleware()

    async def _no_user(_request):
        return None

    middleware = SimpleNamespace(
        enable_auth=True,
        get_user_from_request=lambda _request: None,
        _extract_user_from_run_jwt=_no_user,
        _extract_user_from_device_jwt=_no_user,
    )
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    app = _app()
    app.dependency_overrides[check_admin_permission] = real.check_admin_permission
    app.dependency_overrides[get_current_user] = real.get_current_user
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client() -> TestClient:
    app = _app()
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[get_current_user] = lambda: {"username": "test-user"}
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize(("method", "old", "new"), _MOVES)
def test_the_old_path_answers_308_to_the_new_one(client: TestClient, method: str, old: str, new: str) -> None:
    response = client.request(method, old)
    assert response.status_code == 308
    assert response.headers["location"] == new
    assert response.headers["deprecation"] == "true"
    assert new in response.headers["link"]


def test_the_redirect_keeps_the_query_string(client: TestClient) -> None:
    response = client.get(f"{_KB}/api/knowledge/facts/mine?limit=5&include_shared=true")
    assert response.headers["location"] == f"{_KB}/facts/mine?limit=5&include_shared=true"


def _serves(app: FastAPI, method: str, path: str) -> bool:
    """True when some route fully matches `method` + `path` in registration order."""
    scope = {"type": "http", "method": method, "path": path}
    return any(route.matches(scope)[0] == Match.FULL for route in app.routes)


@pytest.mark.parametrize(("method", "old", "new"), _MOVES)
def test_the_new_path_is_a_served_route(client: TestClient, method: str, old: str, new: str) -> None:
    assert _serves(client.app, method, new)


def test_the_openapi_schema_names_no_doubled_path(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]
    assert paths, "an empty schema would pass the check below vacuously"
    assert not [p for p in paths if f"{_SYSTEM}/api/" in p or f"{_KB}/api/" in p]


def _coordinator() -> Mock:
    coordinator = Mock()
    coordinator.get_cache_stats = Mock(return_value={"total_items": 3})
    coordinator._coordinated_evict = AsyncMock(return_value=7)
    cache = Mock()
    cache.clear = AsyncMock()
    coordinator._caches = {"lru_memory": cache}
    return coordinator


def test_the_coordinator_routes_return_the_handler_response(client: TestClient) -> None:
    fake = AsyncMock(return_value=_coordinator())
    with patch("cache.get_cache_coordinator", fake):
        stats = client.get(f"{_SYSTEM}/cache/coordinator/stats")
        evict = client.post(f"{_SYSTEM}/cache/evict")
        clear = client.post(f"{_SYSTEM}/cache/clear/lru_memory")
        missing = client.post(f"{_SYSTEM}/cache/clear/nope")
    assert (stats.status_code, stats.json()["total_items"]) == (200, 3)
    assert (evict.status_code, evict.json()["evicted"]) == (200, 7)
    assert (clear.status_code, clear.json()["cache"]) == (200, "lru_memory")
    assert missing.status_code == 404


def test_a_post_redirect_followed_by_a_client_replays_the_post(client: TestClient) -> None:
    """308 (not 301/302/303) is what makes a client resend the same method and body."""
    fake = AsyncMock(return_value=_coordinator())
    follower = TestClient(client.app, follow_redirects=True)
    with patch("cache.get_cache_coordinator", fake):
        response = follower.post(f"{_SYSTEM}/api/cache/clear/lru_memory")
    assert response.status_code == 200
    assert response.json()["status"] == "cleared"


_DENIED = (401, 403)


@pytest.mark.parametrize(("method", "old", "new"), _MOVES)
def test_the_new_path_denies_an_anonymous_caller(anonymous: TestClient, method: str, old: str, new: str) -> None:
    """Moving a route must not move it out from under its gate (check_admin_permission or
    get_current_user): with no credentials every new path answers 401/403, never 200/404."""
    response = anonymous.request(method, new)
    assert response.status_code in _DENIED, (new, response.status_code)


@pytest.mark.parametrize(("method", "old", "new"), _MOVES)
def test_a_shim_leaks_no_body(anonymous: TestClient, method: str, old: str, new: str) -> None:
    """The 308 is answered before any gate, so it must carry nothing but the Location."""
    response = anonymous.request(method, old)
    assert response.status_code == 308
    assert response.content == b""
