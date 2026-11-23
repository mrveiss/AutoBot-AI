# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A call-graph cache hit also leaves the persisted summary, so a pre-deploy cached graph is not "not analysed" (#20945)."""

import pytest

from api.codebase_analytics import call_graph_summary as store
from api.codebase_analytics.endpoints import call_graph

CACHED = {
    "summary": {
        "total_functions": 4,
        "total_call_relationships": 5,
        "resolution_rate": 50.0,
        "files_scanned": 2,
        "files_total": 2,
    }
}


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def get(self, key):
        return self.data.get(key)


@pytest.mark.asyncio
async def test_a_cache_hit_with_no_stored_summary_stores_it(monkeypatch, tmp_path):
    redis = FakeRedis()

    async def get_redis(database=None):
        return redis

    async def root(source_id):
        return tmp_path

    async def cached(project_root):
        return CACHED

    monkeypatch.setattr(store, "get_async_redis_client", get_redis)
    monkeypatch.setattr(call_graph, "resolve_scan_root", root)
    monkeypatch.setattr(call_graph, "get_cached_call_graph", cached)
    assert await store.load_call_graph_summary("src-x") is None
    await call_graph.get_call_graph(refresh=False, source_id="src-x")
    loaded = await store.load_call_graph_summary("src-x")
    assert loaded["total_functions"] == 4 and loaded["files_total"] == 2
