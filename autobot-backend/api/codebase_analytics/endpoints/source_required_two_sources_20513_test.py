# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""With two sources registered, a request reads exactly the one it names (#20513).

The shape that was reported: ``/patterns/cached-summary`` with no ``source_id`` substituted the
sentinel ``"default"`` and answered from a partition that is neither the selected source nor all of
them. Here two sources A and B exist, and each route is asked for A, for B, for neither, and for
``*`` -- the Redis-glob value that, unvalidated, builds ``codebase:*:*`` and matches every project.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.codebase_analytics.endpoints import pattern_analysis, stats

_STORAGE_MODULE_NAME = "code_intelligence.pattern_analysis.storage"


@pytest.fixture
def stub_storage():
    original = sys.modules.get(_STORAGE_MODULE_NAME)
    mod = ModuleType(_STORAGE_MODULE_NAME)
    sys.modules[_STORAGE_MODULE_NAME] = mod
    yield mod
    if original is not None:
        sys.modules[_STORAGE_MODULE_NAME] = original
    else:
        sys.modules.pop(_STORAGE_MODULE_NAME, None)


def _client(*routers) -> TestClient:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return TestClient(app)


class _PatternCollection:
    """Two sources' patterns; answers a ``where`` the way the store does."""

    def __init__(self):
        self.where_seen: list[dict] = []
        self._rows = {
            "A": [{"pattern_type": "dup", "severity": "high", "file_path": "a.py", "source_id": "A"}],
            "B": [{"pattern_type": "regex", "severity": "low", "file_path": "b.py", "source_id": "B"}] * 2,
        }

    async def get(self, limit=None, where=None, include=None, offset=None):
        self.where_seen.append(where)
        wanted = where["source_id"] if "source_id" in where else None
        rows = self._rows.get(wanted, [])
        return {"ids": [f"{wanted}-{i}" for i in range(len(rows))], "metadatas": rows}


@pytest.mark.parametrize("source,expected", [("A", 1), ("B", 2)])
def test_cached_summary_filters_to_the_named_source(stub_storage, source, expected):
    collection = _PatternCollection()
    stub_storage.get_pattern_collection_async = AsyncMock(return_value=collection)

    body = _client(pattern_analysis.router).get("/patterns/cached-summary", params={"source_id": source}).json()

    assert collection.where_seen == [{"source_id": source}]
    assert body["total_patterns"] == expected
    assert body["source_id"] == source


def test_stats_reads_the_named_sources_document():
    collection = MagicMock()
    collection.get.return_value = {"metadatas": [{"total_files": "3", "last_indexed": "t"}]}
    with patch.object(stats, "get_code_collection", return_value=collection), patch.object(stats, "indexing_tasks", {}):
        for source in ("A", "B"):
            body = _client(stats.router).get("/stats", params={"source_id": source}).json()
            assert body["source_id"] == source
            assert collection.get.call_args.kwargs["ids"] == [f"codebase_stats_{source}"]


@pytest.mark.parametrize(
    "params", [{}, {"source_id": ""}, {"source_id": "*"}, {"source_id": "a:b"}, {"source_id": "../x"}]
)
def test_a_missing_or_glob_source_is_422_and_reads_nothing(stub_storage, params):
    collection = _PatternCollection()
    stub_storage.get_pattern_collection_async = AsyncMock(return_value=collection)
    stats_collection = MagicMock()
    with patch.object(stats, "get_code_collection", return_value=stats_collection):
        client = _client(pattern_analysis.router, stats.router)
        assert client.get("/patterns/cached-summary", params=params).status_code == 422
        assert client.get("/stats", params=params).status_code == 422

    assert collection.where_seen == []
    stats_collection.get.assert_not_called()
