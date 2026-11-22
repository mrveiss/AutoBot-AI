# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every evolution route requires its source, and its data is that source's alone (#20513)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import analytics_evolution as mod
from api.codebase_analytics.endpoints import shared
from api.schemas_analytics import EvolutionQualitySnapshot, PatternSnapshot

_SNAPSHOT = {
    "timestamp": "2026-11-22T10:00:00+00:00",
    "overall_score": 50,
    "maintainability": 50,
    "testability": 50,
    "documentation": 50,
    "complexity": 50,
    "security": 50,
    "performance": 50,
}


def _routes():
    return [r for r in mod.router.routes if getattr(r, "dependant", None)]


def test_every_evolution_route_requires_source_id():
    routes = _routes()
    assert len(routes) >= 8  # a walk that finds fewer has stopped seeing the routes
    for route in routes:
        query = {q.name: q for q in route.dependant.query_params}
        assert "source_id" in query and query["source_id"].field_info.is_required(), route.path


def test_the_analysis_request_takes_no_repository_path():
    from api.schemas_analytics import EvolutionAnalysisRequest

    assert "repo_path" not in EvolutionAnalysisRequest.model_fields


def test_no_prefix_is_global():
    assert mod._build_evolution_prefixes("a")[0] != mod._build_evolution_prefixes("b")[0]
    for empty in ("", None, "a:b", "*"):
        with pytest.raises(ValueError):
            mod._build_evolution_prefixes(empty)


class _FakeRedis:
    def __init__(self):
        self.values, self.zsets = {}, {}

    def set(self, key, value, ex=None):
        self.values[key] = value

    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)

    def zrangebyscore(self, key, low, high):
        return [k for k, score in self.zsets.get(key, {}).items() if low <= score <= high]


@pytest.mark.asyncio
async def test_a_snapshot_stored_for_source_a_is_not_in_source_b():
    fake = _FakeRedis()
    with patch.object(mod, "get_evolution_redis", return_value=fake):
        assert await mod.store_quality_snapshot(EvolutionQualitySnapshot(**_SNAPSHOT), "a")
        assert await mod.store_pattern_snapshot(
            PatternSnapshot(timestamp=_SNAPSHOT["timestamp"], pattern_type="p", count=1), "a"
        )
    a_prefix, b_prefix = mod._build_evolution_prefixes("a")[0], mod._build_evolution_prefixes("b")[0]
    assert fake.zrangebyscore(f"{a_prefix}timeline", 0, 10**12)
    assert fake.zrangebyscore(f"{b_prefix}timeline", 0, 10**12) == []
    assert all(key.startswith(a_prefix) for key in [*fake.values, *fake.zsets])


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[shared.require_source_access] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("route", ["timeline", "patterns", "trends", "summary", "export"])
def test_a_request_without_source_id_is_a_422(route):
    assert _client().get(f"/{route}").status_code == 422


def test_the_write_routes_require_a_source_too():
    client = _client()
    assert client.post("/snapshot", json=_SNAPSHOT).status_code == 422
    assert client.post("/analyze", json={}).status_code == 422


@pytest.mark.parametrize("route", ["timeline", "patterns", "trends", "summary", "export"])
def test_a_source_with_no_checkout_is_a_404(route):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)):
        assert _client().get(f"/{route}", params={"source_id": "missing"}).status_code == 404


def test_analyze_mines_the_sources_checkout_and_nothing_else(tmp_path):
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)
    miner = MagicMock()
    miner.return_value.analyze_evolution.return_value = {"commits_analyzed": 1}
    with (
        patch.object(shared, "resolve_source_root", AsyncMock(return_value=clone)),
        patch("code_intelligence.code_evolution_miner.CodeEvolutionMiner", miner),
        patch.object(mod, "_store_pattern_snapshots", AsyncMock()),
    ):
        response = _client().post("/analyze", params={"source_id": "src-1"}, json={})
    assert response.status_code == 200
    miner.assert_called_once_with(str(clone))


def test_analyze_refuses_a_checkout_that_is_not_a_git_repository(tmp_path):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=tmp_path)):
        body = _client().post("/analyze", params={"source_id": "src-1"}, json={}).json()
    assert body["status"] == "error"
