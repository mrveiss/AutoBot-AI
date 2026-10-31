# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No route in twenty-one previously ungated routers serves an unauthenticated caller (#16375).

``api.ide_integration``, ``api.knowledge_crawl``, ``api.knowledge_extract``,
``api.knowledge_scrape``, ``api.knowledge_site_map``, ``api.run_jwt_router`` and
``api.web_research_settings``
were mounted with no auth dependency, so every route was reachable anonymously.
Slice 1 of the config-registered remainder adds fourteen more, listed in
``_MOUNTS`` below: the analytics, code-search, validation, resilience and
code-completion routers. Their admin routes are the ones that change shared
state for every user -- a shared index, model, engine setting or tracker.
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
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import api.analytics_llm_patterns as llm_patterns_api
import api.analytics_pattern_learning as pattern_learning_api
import api.code_search as code_search_api
import api.development_speedup as dev_speedup_api
import api.error_resilience as resilience_api
import api.ide_integration as ide_api
import api.knowledge_crawl as crawl_api
import api.knowledge_eval as knowledge_eval_api
import api.knowledge_extract as extract_api
import api.knowledge_scrape as scrape_api
import api.knowledge_site_map as site_map_api
import api.natural_language_search as nl_search_api
import api.phases as phases_api
import api.run_jwt_router as run_jwt_api
import api.search as npu_search_api
import api.system_validation as system_validation_api
import api.validation_dashboard as validation_dashboard_api
import api.web_research_settings as web_research_api
import routers.code_completion as code_completion_api
import routers.feedback as feedback_api
import routers.model_management as model_management_api
from autobot_shared.api_routing.router_routes import effective_routes
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
    (validation_dashboard_api, "/api/validation-dashboard"),
    (dev_speedup_api, "/api/dev-speedup"),
    (system_validation_api, "/api/system-validation"),
    (code_search_api, "/api/code-search"),
    (nl_search_api, "/api/nl-search"),
    (npu_search_api, "/api/npu-search"),
    (llm_patterns_api, "/api/llm-patterns"),
    (pattern_learning_api, "/api/pattern-learning"),
    (resilience_api, "/api"),
    (knowledge_eval_api, "/api/knowledge-test"),
    (phases_api, "/api/phases"),
    (code_completion_api, "/api/code-completion"),
    (feedback_api, "/api/code-completion/feedback"),
    (model_management_api, "/api/code-completion/model"),
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
    # Slice 1 of the config-registered remainder (#16375): admin only where the
    # route changes shared state -- a shared index, model, engine setting or tracker.
    ("GET", "/api/validation-dashboard/status"): _USER,
    ("GET", "/api/validation-dashboard/report"): _USER,
    ("GET", "/api/validation-dashboard/dashboard"): _USER,
    ("GET", "/api/validation-dashboard/dashboard/file"): _USER,
    ("POST", "/api/validation-dashboard/generate"): _ADMIN,
    ("GET", "/api/validation-dashboard/metrics"): _USER,
    ("GET", "/api/validation-dashboard/trends"): _USER,
    ("GET", "/api/validation-dashboard/alerts"): _USER,
    ("GET", "/api/validation-dashboard/recommendations"): _USER,
    ("POST", "/api/validation-dashboard/judge_workflow_step"): _USER,
    ("POST", "/api/validation-dashboard/judge_agent_response"): _USER,
    ("GET", "/api/validation-dashboard/judge_status"): _USER,
    ("POST", "/api/dev-speedup/analyze"): _USER,
    ("GET", "/api/dev-speedup/analyze"): _USER,
    ("GET", "/api/dev-speedup/duplicates"): _USER,
    ("GET", "/api/dev-speedup/patterns"): _USER,
    ("GET", "/api/dev-speedup/imports"): _USER,
    ("GET", "/api/dev-speedup/dead-code"): _USER,
    ("GET", "/api/dev-speedup/refactoring"): _USER,
    ("GET", "/api/dev-speedup/quality"): _USER,
    ("GET", "/api/dev-speedup/recommendations"): _USER,
    ("GET", "/api/dev-speedup/status"): _USER,
    ("GET", "/api/dev-speedup/examples"): _USER,
    ("GET", "/api/dev-speedup/templates"): _USER,
    ("GET", "/api/dev-speedup/history"): _USER,
    ("POST", "/api/system-validation/validate/comprehensive"): _USER,
    ("GET", "/api/system-validation/validate/quick"): _USER,
    ("GET", "/api/system-validation/validate/component/{component_name}"): _USER,
    ("GET", "/api/system-validation/validate/recommendations"): _USER,
    ("GET", "/api/system-validation/validate/status"): _USER,
    ("POST", "/api/system-validation/validate/benchmark"): _USER,
    ("POST", "/api/code-search/index"): _ADMIN,
    ("POST", "/api/code-search/search"): _USER,
    ("GET", "/api/code-search/search"): _USER,
    ("GET", "/api/code-search/status"): _USER,
    ("DELETE", "/api/code-search/cache"): _ADMIN,
    ("GET", "/api/code-search/examples"): _USER,
    ("POST", "/api/code-search/analytics/declarations"): _USER,
    ("POST", "/api/code-search/analytics/duplicates"): _USER,
    ("GET", "/api/code-search/analytics/stats"): _USER,
    ("POST", "/api/code-search/analytics/refactor-suggestions"): _USER,
    ("POST", "/api/nl-search/search"): _USER,
    ("POST", "/api/nl-search/parse"): _USER,
    ("GET", "/api/nl-search/suggestions"): _USER,
    ("POST", "/api/nl-search/explain"): _USER,
    ("GET", "/api/nl-search/intents"): _USER,
    ("GET", "/api/nl-search/domains"): _USER,
    ("POST", "/api/npu-search/semantic"): _USER,
    ("GET", "/api/npu-search/hardware/status"): _USER,
    ("POST", "/api/npu-search/benchmark"): _USER,
    ("POST", "/api/npu-search/optimize"): _ADMIN,
    ("GET", "/api/npu-search/performance/analytics"): _USER,
    ("GET", "/api/npu-search/test/connectivity"): _USER,
    ("POST", "/api/llm-patterns/analyze"): _USER,
    ("POST", "/api/llm-patterns/record"): _USER,
    ("GET", "/api/llm-patterns/stats"): _USER,
    ("GET", "/api/llm-patterns/cache-opportunities"): _USER,
    ("GET", "/api/llm-patterns/recommendations"): _USER,
    ("GET", "/api/llm-patterns/model-comparison"): _USER,
    ("GET", "/api/llm-patterns/category-distribution"): _USER,
    ("GET", "/api/llm-patterns/cost-breakdown"): _USER,
    ("POST", "/api/pattern-learning/feedback"): _USER,
    ("GET", "/api/pattern-learning/confidence"): _USER,
    ("GET", "/api/pattern-learning/metrics"): _USER,
    ("GET", "/api/pattern-learning/active-learning"): _USER,
    ("POST", "/api/pattern-learning/patterns"): _ADMIN,
    ("GET", "/api/pattern-learning/patterns/{pattern_id}/history"): _USER,
    ("POST", "/api/pattern-learning/learn"): _ADMIN,
    ("GET", "/api/resilience/circuit-breakers"): _USER,
    ("GET", "/api/resilience/error-budgets"): _USER,
    ("POST", "/api/resilience/circuit-breakers/{service_name}/reset"): _ADMIN,
    ("POST", "/api/resilience/error-budgets/{component}/reset"): _ADMIN,
    ("GET", "/api/knowledge-test/test/fresh_stats"): _USER,
    ("POST", "/api/knowledge-test/test/rebuild_index"): _ADMIN,
    ("GET", "/api/phases/status"): _USER,
    ("POST", "/api/phases/validation/run"): _ADMIN,
    ("POST", "/api/code-completion/extract"): _ADMIN,
    ("GET", "/api/code-completion/patterns"): _USER,
    ("GET", "/api/code-completion/patterns/{category}"): _USER,
    ("POST", "/api/code-completion/patterns/search"): _USER,
    ("GET", "/api/code-completion/statistics"): _USER,
    ("POST", "/api/code-completion/context/analyze"): _USER,
    ("GET", "/api/code-completion/context/{context_id}"): _USER,
    ("POST", "/api/code-completion/feedback/"): _USER,
    ("GET", "/api/code-completion/feedback/metrics"): _USER,
    ("GET", "/api/code-completion/feedback/recent"): _USER,
    ("POST", "/api/code-completion/feedback/retrain"): _ADMIN,
    ("GET", "/api/code-completion/feedback/statistics"): _USER,
    ("POST", "/api/code-completion/model/train"): _ADMIN,
    ("GET", "/api/code-completion/model/models"): _USER,
    ("GET", "/api/code-completion/model/models/{version}"): _USER,
    ("POST", "/api/code-completion/model/models/{version}/activate"): _ADMIN,
    ("GET", "/api/code-completion/model/evaluate"): _USER,
    ("POST", "/api/code-completion/model/predict"): _USER,
}
_PATH_VALUES = {
    "{run_id}": "run-1",
    "{component_name}": "redis",
    "{service_name}": "svc",
    "{component}": "comp",
    "{pattern_id}": "p1",
    "{category}": "cat",
    "{context_id}": "ctx",
    "{version}": "v1",
}
_NON_ADMIN = {"username": "viewer", "role": "user"}


def _app() -> FastAPI:
    app = FastAPI()
    for module, prefix in _MOUNTS:
        app.include_router(module.router, prefix=prefix)
    return app


def _routes() -> set:
    """Served ``(method, path)`` pairs, read per router rather than off the app (#15093).

    On fastapi>=0.139 ``app.routes`` holds one opaque wrapper per include and no
    ``APIRoute``, so walking the app finds nothing. Each router here is a leaf, so
    its own routes plus the prefix it is mounted at are exactly the served paths.
    """
    found = set()
    for module, prefix in _MOUNTS:
        for mounted in effective_routes(module.router):
            assert mounted.prefix_complete, mounted.path
            if isinstance(mounted.route, APIRoute):
                found.update((method, prefix + mounted.path) for method in mounted.methods)
    return found


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


#: Slice 1 contrast (#16375): one user-level route per router that takes a body.
#: A list where the body model expects an object fails validation, which FastAPI
#: checks only AFTER every dependency has passed -- so a 422 proves the gate let
#: the caller through without running the handler and its side effects.
_SLICE_1_USER_BODY_ROUTES = (
    "/api/validation-dashboard/judge_workflow_step",
    "/api/dev-speedup/analyze",
    "/api/system-validation/validate/comprehensive",
    "/api/code-search/search",
    "/api/nl-search/search",
    "/api/npu-search/semantic",
    "/api/llm-patterns/analyze",
    "/api/pattern-learning/feedback",
    "/api/code-completion/patterns/search",
    "/api/code-completion/feedback/",
    "/api/code-completion/model/predict",
)

#: The same probe on every slice-1 admin route that takes a body, as an admin.
_SLICE_1_ADMIN_BODY_ROUTES = (
    "/api/validation-dashboard/generate",
    "/api/code-search/index",
    "/api/npu-search/optimize",
    "/api/pattern-learning/patterns",
    "/api/code-completion/extract",
    "/api/code-completion/feedback/retrain",
    "/api/code-completion/model/train",
)


@pytest.mark.parametrize("path", _SLICE_1_USER_BODY_ROUTES)
def test_a_non_admin_passes_the_gate_of_a_slice_1_user_route(client, path: str) -> None:
    test_client, identity = client
    identity.user = dict(_NON_ADMIN)

    assert test_client.post(path, json=[]).status_code == 422


@pytest.mark.parametrize("path", _SLICE_1_ADMIN_BODY_ROUTES)
def test_an_admin_passes_the_gate_of_a_slice_1_admin_route(client, path: str) -> None:
    test_client, identity = client
    identity.user = {"username": "root", "role": "admin"}

    assert test_client.post(path, json=[]).status_code == 422


def test_the_bodiless_slice_1_routers_admit_their_own_callers(client, monkeypatch) -> None:
    """Resilience, phases and knowledge-test take no body, so their handlers are stubbed."""
    test_client, identity = client
    breakers = SimpleNamespace(get_status=lambda: {}, reset_breaker=lambda _name: None)
    monkeypatch.setattr(resilience_api, "get_circuit_breaker_manager", lambda: breakers)
    state = SimpleNamespace(get_project_status=lambda use_cache=True: {"phases": {}})
    monkeypatch.setattr(phases_api, "get_project_state_manager", lambda: state)
    # #18122 D5: the route reads the canonical instance, so the accessor is the seam.
    monkeypatch.setattr(knowledge_eval_api, "get_knowledge_base_async", AsyncMock(return_value=_FakeKnowledgeBase()))

    identity.user = dict(_NON_ADMIN)
    for path in ("/api/resilience/circuit-breakers", "/api/phases/status", "/api/knowledge-test/test/fresh_stats"):
        assert test_client.get(path).status_code == 200, path
    identity.user = {"username": "root", "role": "admin"}
    assert test_client.post("/api/resilience/circuit-breakers/svc/reset").status_code == 200


class _FakeKnowledgeBase:
    async def get_stats(self) -> dict:
        return {}
