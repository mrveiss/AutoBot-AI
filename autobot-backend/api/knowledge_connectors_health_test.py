# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Tests for GET /api/knowledge_base/connectors/health — Issue #4420.

Covers:
  - empty registry returns empty structure
  - healthy + unhealthy aggregation with realistic labels
  - exceptions surfaced in ``errors``
  - hydration degrades to in-memory registry when Redis is down (Issue #5054)
  - hydration skips corrupted connector records and continues (Issue #5055)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from api.knowledge_connectors import _hydrate_all_instances, router
from auth_middleware import check_admin_permission
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import ConnectorRegistry
from tests.helpers.fake_connector import FakeConnector


def _make_app() -> FastAPI:
    app = FastAPI()
    # Skip auth for unit tests
    app.dependency_overrides[check_admin_permission] = lambda: None
    app.include_router(router, prefix="/api")
    return app


def _make_cfg(connector_id: str, connector_type: str, name: str) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id=connector_id,
        connector_type=connector_type,
        name=name,
        config={},
    )


@pytest.fixture(autouse=True)
def _clear_registry():
    ConnectorRegistry._instances.clear()
    yield
    ConnectorRegistry._instances.clear()


def test_health_endpoint_empty_registry():
    app = _make_app()
    client = TestClient(app)

    async def _no_op():
        return None

    # Bypass Redis hydration entirely for this unit test.
    with patch("api.knowledge_connectors._hydrate_all_instances", new=_no_op):
        resp = client.get("/api/knowledge_base/connectors/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["healthy"] == []
    assert body["unavailable"] == []
    assert body["errors"] == {}
    assert "checked_at" in body


def test_health_endpoint_aggregates_mixed_results():
    app = _make_app()
    client = TestClient(app)

    ConnectorRegistry.add_instance(FakeConnector(_make_cfg("a", "file_server", "docs-nfs"), result=True))
    ConnectorRegistry.add_instance(FakeConnector(_make_cfg("b", "web_crawler", "internal-wiki"), result=True))
    ConnectorRegistry.add_instance(
        FakeConnector(
            _make_cfg("c", "notion", "workspace-1"),
            result=RuntimeError("401 Unauthorized"),
        )
    )

    async def _no_op():
        return None

    with patch("api.knowledge_connectors._hydrate_all_instances", new=_no_op):
        resp = client.get("/api/knowledge_base/connectors/health")

    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["healthy"]) == [
        "file_server:docs-nfs",
        "web_crawler:internal-wiki",
    ]
    assert body["unavailable"] == ["notion:workspace-1"]
    assert "401 Unauthorized" in body["errors"]["notion:workspace-1"]
    assert "checked_at" in body


def test_health_route_matched_before_connector_id_path():
    """Ensure FastAPI dispatches /health to the aggregate endpoint,
    not /{connector_id} (Issue #4420 route-ordering guard)."""
    app = _make_app()
    client = TestClient(app)

    async def _no_op():
        return None

    with patch("api.knowledge_connectors._hydrate_all_instances", new=_no_op):
        resp = client.get("/api/knowledge_base/connectors/health")

    # If dispatched to GET /{connector_id}, we'd get 404 "connector not found".
    assert resp.status_code == 200
    assert "healthy" in resp.json()


# ---------------------------------------------------------------------------
# Issue #5054 / #5055: hydration resiliency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hydration_returns_gracefully_when_redis_down():
    """Issue #5054: Redis failure must not propagate out of hydration."""
    with patch(
        "api.knowledge_connectors._list_connector_ids",
        new=AsyncMock(side_effect=RedisError("connection refused")),
    ):
        # Should return without raising, allowing the caller to fall back
        # to the in-memory registry.
        await _hydrate_all_instances()


@pytest.mark.asyncio
async def test_hydration_returns_gracefully_on_connection_error():
    """Issue #5054: OSError/ConnectionError from the Redis client must also
    be caught so the health endpoint stays usable."""
    with patch(
        "api.knowledge_connectors._list_connector_ids",
        new=AsyncMock(side_effect=ConnectionError("ECONNREFUSED")),
    ):
        await _hydrate_all_instances()


def test_health_endpoint_works_when_redis_hydration_fails():
    """Issue #5054: /connectors/health must return 200 using the in-memory
    registry even when Redis is unreachable during hydration."""
    app = _make_app()
    client = TestClient(app)

    ConnectorRegistry.add_instance(FakeConnector(_make_cfg("in-mem", "file_server", "local-only"), result=True))

    with patch(
        "api.knowledge_connectors._list_connector_ids",
        new=AsyncMock(side_effect=RedisError("down")),
    ):
        resp = client.get("/api/knowledge_base/connectors/health")

    assert resp.status_code == 200
    body = resp.json()
    assert "file_server:local-only" in body["healthy"]
    assert body["errors"] == {}


@pytest.mark.asyncio
async def test_hydration_skips_corrupted_record_and_continues():
    """Issue #5055: a single bad connector record must not abort the loop —
    subsequent connectors still load into the registry."""
    ConnectorRegistry._instances.clear()

    async def _fake_list_ids():
        return ["bad", "good"]

    good_cfg = _make_cfg("good", "file_server", "healthy-share")

    async def _fake_load(cid: str):
        if cid == "bad":
            raise ValueError("invalid JSON / missing required field")
        return good_cfg

    with (
        patch("api.knowledge_connectors._list_connector_ids", new=_fake_list_ids),
        patch("api.knowledge_connectors._load_connector", new=_fake_load),
        patch("api.knowledge_connectors._load_or_create_instance") as mock_load_or_create,
    ):
        await _hydrate_all_instances()

    # The good connector must still have been processed after the bad one raised.
    mock_load_or_create.assert_called_once_with(good_cfg)
