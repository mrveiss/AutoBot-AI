# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every quality route requires its source, and its data is that source's alone (#20513)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import analytics_quality as mod
from api.codebase_analytics.endpoints import shared

#: Not about one source: the remediation loop's own history (written with no source).
_NOT_SOURCE_SCOPED = {"/remediation-deltas"}
_SCOPED_READS = ("health-score", "metrics", "patterns", "complexity", "trends", "snapshot", "export")


def _client(real_access: bool = False):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[check_admin_permission] = lambda: True
    if not real_access:
        app.dependency_overrides[shared.require_source_access] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def test_every_source_scoped_quality_route_requires_source_id():
    seen = 0
    for route in mod.router.routes:
        if route.path in _NOT_SOURCE_SCOPED or not getattr(route, "dependant", None):
            continue
        query = {q.name: q for q in route.dependant.query_params}
        assert "source_id" in query and query["source_id"].field_info.is_required(), route.path
        seen += 1
    assert seen >= 8  # health-score, metrics, patterns, complexity, trends, snapshot, drill-down, export, ws


@pytest.mark.parametrize("route", [*_SCOPED_READS, "drill-down/complexity"])
def test_a_request_without_source_id_is_a_422(route):
    assert _client().get(f"/{route}").status_code == 422


@pytest.mark.parametrize("route", [*_SCOPED_READS, "drill-down/complexity"])
def test_a_source_with_no_checkout_is_a_404(route):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)):
        assert _client().get(f"/{route}", params={"source_id": "missing"}).status_code == 404


@pytest.mark.parametrize("route", [*_SCOPED_READS, "drill-down/complexity"])
def test_a_foreign_private_source_is_a_404_with_access_enforcement_left_real(route, tmp_path):
    from api.codebase_analytics.source_models import CodeSource, SourceAccess

    private = CodeSource(name="p", clone_path="/tmp/p", owner_id="alice", access=SourceAccess.PRIVATE)
    with (
        patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "mallory"})),
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=private)),
        patch.object(shared, "resolve_source_root", AsyncMock(return_value=tmp_path)),
    ):
        assert _client(real_access=True).get(f"/{route}", params={"source_id": "x"}).status_code == 404


class _FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value


@pytest.mark.asyncio
async def test_source_a_cached_quality_is_not_served_to_source_b(tmp_path):
    fake = _FakeRedis()
    calc = AsyncMock(side_effect=lambda source_root, source_id: {"metrics": {"x": 1}, "who": source_id})
    with (
        patch("autobot_shared.redis_client.get_redis_client", return_value=fake),
        patch.object(mod, "calculate_real_quality_metrics", calc),
    ):
        a = await mod.get_quality_data_from_storage(tmp_path, "a")
        b = await mod.get_quality_data_from_storage(tmp_path, "b")
    assert (a["who"], b["who"]) == ("a", "b")
    assert calc.await_count == 2
    assert sorted(fake.values) == ["code_quality:latest:a", "code_quality:latest:b"]


@pytest.mark.asyncio
async def test_health_history_is_kept_per_source():
    redis = MagicMock()
    redis.zadd, redis.zremrangebyrank = AsyncMock(), AsyncMock()
    with patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=redis)):
        await mod._persist_health_snapshot(70.0, {"a": 1.0}, "a")
    assert redis.zadd.call_args.args[0] == mod._health_history_key("a")
    assert mod._health_history_key("a") != mod._health_history_key("b")
    with pytest.raises(ValueError):
        mod._health_history_key("")


@pytest.mark.asyncio
async def test_the_problem_query_names_the_source():
    collection = MagicMock()
    collection.get = AsyncMock(return_value={"metadatas": []})
    with patch("api.codebase_analytics.storage.get_code_collection_async", AsyncMock(return_value=collection)):
        await mod._get_problems_from_chromadb(Path("/tmp/p"), "src-1")
    where = collection.get.await_args_list[0].kwargs["where"]
    assert {"source_id": "src-1"} in where["$and"] and {"type": "problem"} in where["$and"]
