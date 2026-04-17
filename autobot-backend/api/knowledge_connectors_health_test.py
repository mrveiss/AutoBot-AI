# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Tests for GET /api/knowledge_base/connectors/health — Issue #4420.

Covers:
  - empty registry returns empty structure
  - healthy + unhealthy aggregation with realistic labels
  - exceptions surfaced in ``errors``
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.knowledge_connectors import router
from auth_middleware import check_admin_permission
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import ConnectorRegistry


class _FakeConnector:
    def __init__(self, config: ConnectorConfig, result=True):
        self.config = config
        self._result = result

    async def test_connection(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


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

    ConnectorRegistry.add_instance(
        _FakeConnector(_make_cfg("a", "file_server", "docs-nfs"), result=True)
    )
    ConnectorRegistry.add_instance(
        _FakeConnector(_make_cfg("b", "web_crawler", "internal-wiki"), result=True)
    )
    ConnectorRegistry.add_instance(
        _FakeConnector(
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
