# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wiring test for the /api/health/celery-dead-letter endpoint (#11586).

Verifies the dead-letter health endpoint is registered by
``register_root_endpoints`` (called from app_factory) and returns the parked
count + recent entries produced by ``utils.celery_reliability``.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app() -> FastAPI:
    from initialization.endpoints import register_root_endpoints

    app = FastAPI()
    register_root_endpoints(app)
    return app


def test_celery_dead_letter_route_registered():
    """The endpoint must be present among the root health routes."""
    app = _build_app()
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/health/celery-dead-letter" in paths


def test_celery_dead_letter_endpoint_returns_status(monkeypatch):
    """The endpoint must surface count + recent entries from the accessor."""
    import utils.celery_reliability as cr

    async def _fake_status(limit: int = 20):
        return {
            "available": True,
            "parked": 2,
            "recent": [{"task_id": "p-1", "status": "parked"}][:limit],
        }

    monkeypatch.setattr(cr, "get_dead_letter_status", _fake_status)

    app = _build_app()
    with TestClient(app) as client:
        response = client.get("/api/health/celery-dead-letter")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["parked"] == 2
    assert body["recent"][0]["task_id"] == "p-1"
    assert "timestamp" in body
