# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No route in seven previously ungated routers serves an unauthenticated caller (#16375).

``api.ide_integration``, ``api.knowledge_crawl``, ``api.knowledge_extract``,
``api.knowledge_scrape``, ``api.knowledge_site_map``, ``api.run_jwt_router`` and
``api.web_research_settings``
were mounted with no auth dependency, so every route was reachable anonymously.
Each router now depends on ``get_current_user`` at router level, so every route
needs a signed-in caller. Owner decision: crawl/scrape/site-map/extract are for
any signed-in user; only routes that change shared config (IDE config, the
web-research settings mutations) also depend on ``check_admin_permission``.

These tests judge that with the REAL dependencies, the way
``test_skills_auth_16368.py`` does. Under pytest, ``auth_middleware`` is the
conftest stub, whose ``get_current_user`` always returns an admin, so the routers'
``Depends(...)`` captured stub callables. Each test overrides exactly the objects
the router modules bound with the real functions from ``real_auth_middleware``,
and controls only the identity the real code reads.
"""

from types import SimpleNamespace
from typing import Dict, Tuple

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import api.ide_integration as ide_api
import api.knowledge_crawl as crawl_api
import api.knowledge_extract as extract_api
import api.knowledge_scrape as scrape_api
import api.knowledge_site_map as site_map_api
import api.run_jwt_router as run_jwt_api
import api.web_research_settings as web_research_api
from web_fetch import FetchResult
from web_fetch.site_mapper import SiteMapResult

_ADMIN, _USER = "admin", "user"

#: Each router with the prefix the app factory mounts it under (``/api`` plus
#: its registry prefix, ``feature_routers.py``).
_MOUNTS = (
    (ide_api, "/api/ide"),
    (crawl_api, "/api/knowledge"),
    (scrape_api, "/api/knowledge"),
    (site_map_api, "/api/knowledge"),
    (extract_api, "/api/knowledge"),
    (run_jwt_api, "/api"),
    (web_research_api, "/api"),
)

#: The per-route policy, pinned. A route added to any of these routers fails
#: ``test_the_policy_table_covers_every_route`` until it is classified here.
_POLICY: Dict[Tuple[str, str], str] = {
    ("POST", "/api/ide/analyze"): _USER,
    ("POST", "/api/ide/quickfix"): _USER,
    ("POST", "/api/ide/hover"): _USER,
    ("GET", "/api/ide/rules"): _USER,
    ("PUT", "/api/ide/config"): _ADMIN,
    ("GET", "/api/ide/categories"): _USER,
    ("GET", "/api/ide/severities"): _USER,
    ("POST", "/api/ide/batch-analyze"): _USER,
    ("POST", "/api/ide/completion"): _USER,
    # Owner decision (#16375 PR discussion): the research routes are for any
    # signed-in user — only the web-research settings mutations stay admin.
    ("POST", "/api/knowledge/crawl"): _USER,
    ("POST", "/api/knowledge/scrape"): _USER,
    ("POST", "/api/knowledge/site-map"): _USER,
    ("POST", "/api/knowledge/extract"): _USER,
    ("POST", "/api/runs/{run_id}/jwt/refresh"): _USER,
    ("GET", "/api/web-research/status"): _USER,
    ("POST", "/api/web-research/enable"): _ADMIN,
    ("POST", "/api/web-research/disable"): _ADMIN,
    ("GET", "/api/web-research/settings"): _USER,
    ("PUT", "/api/web-research/settings"): _ADMIN,
    ("POST", "/api/web-research/test"): _ADMIN,
    ("POST", "/api/web-research/clear-cache"): _ADMIN,
    ("POST", "/api/web-research/reset-circuit-breakers"): _ADMIN,
    ("GET", "/api/web-research/usage-stats"): _USER,
}
_PATH_VALUES = {"{run_id}": "run-1"}
_NON_ADMIN = {"username": "viewer", "role": "user"}


def _app() -> FastAPI:
    app = FastAPI()
    for module, prefix in _MOUNTS:
        app.include_router(module.router, prefix=prefix)
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
    for module, _prefix in _MOUNTS:
        app.dependency_overrides[module.get_current_user] = real_auth_middleware.get_current_user
        if hasattr(module, "check_admin_permission"):
            app.dependency_overrides[module.check_admin_permission] = real_auth_middleware.check_admin_permission
    return TestClient(app), identity


def test_the_policy_table_covers_every_route() -> None:
    """A route added to any of the six routers must be classified here before it ships."""
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

    response = _call(test_client, "GET", "/api/ide/categories")

    assert response.status_code == 200, response.text


_RESEARCH_ROUTES = (
    ("POST", "/api/knowledge/crawl"),
    ("POST", "/api/knowledge/scrape"),
    ("POST", "/api/knowledge/site-map"),
    ("POST", "/api/knowledge/extract"),
)


@pytest.fixture
def _stub_research_io(monkeypatch):
    """Stub each research route's outbound call, so only the auth gate is under test."""

    async def _fake_crawl(self, **_kwargs):
        return []

    async def _fake_fetch(url, **_kwargs):
        return FetchResult(url=url, success=True, markdown="stub")

    async def _fake_map_site(domain, **_kwargs):
        return SiteMapResult(domain=domain, source="sitemap", entries=[])

    async def _fake_extract_url(url, schema, render):
        return {"url": url, "data": {}, "schema_valid": True}

    monkeypatch.setattr(crawl_api.WebCrawlerConnector, "crawl", _fake_crawl)
    monkeypatch.setattr(scrape_api.WebFetcher, "fetch", _fake_fetch)
    monkeypatch.setattr(site_map_api.SiteMapper, "map_site", _fake_map_site)
    monkeypatch.setattr(extract_api, "extract_url", _fake_extract_url)


@pytest.mark.parametrize(("method", "path"), _RESEARCH_ROUTES)
def test_a_non_admin_reaches_the_research_routes(client, _stub_research_io, method: str, path: str) -> None:
    """Owner decision: crawl/scrape/site-map/extract are for any signed-in user, not admin only."""
    test_client, identity = client
    identity.user = dict(_NON_ADMIN)

    body = {"seeds": ["https://example.com"]} if path.endswith("/crawl") else {"url": "https://example.com"}
    if path.endswith("/site-map"):
        body = {"domain": "example.com"}
    elif path.endswith("/extract"):
        body["schema"] = {"type": "object"}

    response = test_client.request(method, path, json=body)

    assert response.status_code == 200, response.text
