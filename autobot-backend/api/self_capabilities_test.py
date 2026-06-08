# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for api/self_capabilities.py (Issue #3295).

Covers:
- Endpoint entry builder
- Tag and operation-type categorisation helpers
- Cache validity logic
- discover_endpoints() behaviour (stub app)
"""

import time
from unittest.mock import MagicMock, patch

import pytest

import api.self_capabilities as sc

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_route(
    path: str,
    method: str = "GET",
    tags: list | None = None,
    summary: str = "Test",
) -> dict:
    """Build a minimal OpenAPI path-item dict for one operation."""
    return {
        path: {
            method.lower(): {
                "summary": summary,
                "tags": tags or ["test"],
                "operationId": f"{method.lower()}_{path.strip('/').replace('/', '_')}",
            }
        }
    }


def _stub_app(route_count: int = 5) -> MagicMock:
    """Minimal FastAPI app mock."""
    app = MagicMock()
    app.title = "TestApp"
    app.version = "0.0.1"
    app.description = ""
    app.routes = [object() for _ in range(route_count)]
    return app


# ---------------------------------------------------------------------------
# _build_endpoint_entry
# ---------------------------------------------------------------------------


def test_build_endpoint_entry_maps_method_and_operation_type():
    op = {"summary": "Fetch item", "tags": ["items"], "operationId": "get_item"}
    entry = sc._build_endpoint_entry("/api/items/{id}", "get", op)

    assert entry["path"] == "/api/items/{id}"
    assert entry["method"] == "GET"
    assert entry["operation_type"] == "query"
    assert entry["summary"] == "Fetch item"
    assert entry["tags"] == ["items"]


def test_build_endpoint_entry_post_is_create():
    op = {"summary": "Create", "tags": ["items"]}
    entry = sc._build_endpoint_entry("/api/items", "post", op)
    assert entry["operation_type"] == "create"


def test_build_endpoint_entry_delete_is_delete():
    op = {}
    entry = sc._build_endpoint_entry("/api/items/1", "delete", op)
    assert entry["operation_type"] == "delete"
    assert entry["tags"] == ["untagged"]


# ---------------------------------------------------------------------------
# _collect_endpoints
# ---------------------------------------------------------------------------


def test_collect_endpoints_filters_non_http_keys():
    paths = {
        "/api/x": {
            "get": {"summary": "ok", "tags": ["x"]},
            "parameters": [{"name": "q"}],  # must be ignored
        }
    }
    endpoints = sc._collect_endpoints(paths)
    assert len(endpoints) == 1
    assert endpoints[0]["method"] == "GET"


def test_collect_endpoints_multiple_methods():
    paths = {
        "/api/y": {
            "get": {"summary": "get", "tags": ["y"]},
            "post": {"summary": "create", "tags": ["y"]},
        }
    }
    endpoints = sc._collect_endpoints(paths)
    assert len(endpoints) == 2
    methods = {e["method"] for e in endpoints}
    assert methods == {"GET", "POST"}


# ---------------------------------------------------------------------------
# _categorise_by_tag
# ---------------------------------------------------------------------------


def test_categorise_by_tag_groups_correctly():
    endpoints = [
        {"path": "/a", "method": "GET", "tags": ["alpha"], "operation_type": "query"},
        {"path": "/b", "method": "POST", "tags": ["alpha"], "operation_type": "create"},
        {"path": "/c", "method": "GET", "tags": ["beta"], "operation_type": "query"},
    ]
    by_tag = sc._categorise_by_tag(endpoints)
    assert set(by_tag.keys()) == {"alpha", "beta"}
    assert len(by_tag["alpha"]) == 2
    assert len(by_tag["beta"]) == 1


def test_categorise_by_tag_no_duplicate_entries():
    endpoints = [
        {"path": "/dup", "method": "GET", "tags": ["t"], "operation_type": "query"},
        {"path": "/dup", "method": "GET", "tags": ["t"], "operation_type": "query"},
    ]
    by_tag = sc._categorise_by_tag(endpoints)
    assert len(by_tag["t"]) == 1


# ---------------------------------------------------------------------------
# _categorise_by_operation
# ---------------------------------------------------------------------------


def test_categorise_by_operation_type():
    endpoints = [
        {"path": "/a", "method": "GET", "tags": [], "operation_type": "query"},
        {"path": "/b", "method": "GET", "tags": [], "operation_type": "query"},
        {"path": "/c", "method": "POST", "tags": [], "operation_type": "create"},
    ]
    by_op = sc._categorise_by_operation(endpoints)
    assert len(by_op["query"]) == 2
    assert len(by_op["create"]) == 1


# ---------------------------------------------------------------------------
# _cache_is_valid
# ---------------------------------------------------------------------------


def test_cache_is_valid_returns_false_when_no_cache():
    sc._cache = None
    assert sc._cache_is_valid("abc") is False


def test_cache_is_valid_returns_false_after_ttl(monkeypatch):
    sc._cache = {"total_endpoints": 1}
    sc._cache_ts = time.monotonic() - (sc._CACHE_TTL + 10)
    sc._cache_schema_hash = "abc"
    assert sc._cache_is_valid("abc") is False


def test_cache_is_valid_returns_false_on_hash_mismatch():
    sc._cache = {"total_endpoints": 1}
    sc._cache_ts = time.monotonic()
    sc._cache_schema_hash = "old"
    assert sc._cache_is_valid("new") is False


def test_cache_is_valid_returns_true_when_fresh():
    sc._cache = {"total_endpoints": 1}
    sc._cache_ts = time.monotonic()
    sc._cache_schema_hash = "match"
    assert sc._cache_is_valid("match") is True


# ---------------------------------------------------------------------------
# discover_endpoints (integration-style with stub)
# ---------------------------------------------------------------------------


def _fake_openapi_paths(_app):
    return {
        "/api/items": {
            "get": {"summary": "List items", "tags": ["items"]},
            "post": {"summary": "Create item", "tags": ["items"]},
        },
        "/api/system/health": {
            "get": {"summary": "Health", "tags": ["system"]},
        },
    }


@pytest.mark.asyncio
async def test_discover_endpoints_returns_correct_structure():
    # Reset cache state
    sc._cache = None
    sc._cache_ts = 0.0
    sc._cache_schema_hash = ""

    app = _stub_app(route_count=10)

    with patch.object(sc, "_openapi_paths", _fake_openapi_paths):
        result = await sc.discover_endpoints(app)

    assert result["total_endpoints"] == 3
    assert result["unique_paths"] == 2
    assert "items" in result["by_tag"]
    assert "system" in result["by_tag"]
    assert "query" in result["by_operation_type"]
    assert "create" in result["by_operation_type"]
    assert "/api/items" in result["api_paths"]


@pytest.mark.asyncio
async def test_discover_endpoints_uses_cache_on_second_call():
    sc._cache = None
    sc._cache_ts = 0.0
    sc._cache_schema_hash = ""

    app = _stub_app(route_count=7)
    call_count = 0

    def counting_paths(a):
        nonlocal call_count
        call_count += 1
        return _fake_openapi_paths(a)

    with patch.object(sc, "_openapi_paths", counting_paths):
        await sc.discover_endpoints(app)
        await sc.discover_endpoints(app)

    assert call_count == 1, "Schema should only be built once when route count is stable"


@pytest.mark.asyncio
async def test_discover_endpoints_refreshes_on_route_count_change():
    sc._cache = None
    sc._cache_ts = 0.0
    sc._cache_schema_hash = ""

    app = _stub_app(route_count=5)
    call_count = 0

    def counting_paths(a):
        nonlocal call_count
        call_count += 1
        return _fake_openapi_paths(a)

    with patch.object(sc, "_openapi_paths", counting_paths):
        await sc.discover_endpoints(app)

        # Simulate new router being added
        app.routes = [object() for _ in range(10)]
        await sc.discover_endpoints(app)

    assert call_count == 2, "Schema must refresh when route count changes"
