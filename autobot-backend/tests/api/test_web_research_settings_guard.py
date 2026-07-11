# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WebResearcher availability guard for /api/web-research/* (#11665).

Phase-2 startup failure leaves ``app.state.web_researcher = None``
(initialization/lifespan.py). Every endpoint that needs the researcher must
answer 503 with an actionable detail instead of AttributeError-ing on an
uninitialized instance. Also pins the canonical (un-stacked) route paths.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.web_research_settings import _RESEARCHER_UNAVAILABLE_DETAIL, router


def _client(researcher) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.web_researcher = researcher
    return TestClient(app)


def _mock_researcher() -> MagicMock:
    researcher = MagicMock()
    researcher.health_check = AsyncMock(return_value={"enabled": True})
    researcher.get_circuit_breaker_status = MagicMock(return_value={})
    researcher.get_cache_stats = MagicMock(return_value={"cache_size": 0, "cache_ttl": 300, "rate_limiter": {}})
    researcher.enabled = True
    return researcher


def test_router_uses_canonical_web_research_paths() -> None:
    """Router self-prefixes /web-research; registry adds no extra prefix (#11665)."""
    paths = {route.path for route in router.routes}
    assert all(path.startswith("/web-research/") for path in paths)
    assert "/web-research/status" in paths
    assert "/web-research/settings" in paths


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/web-research/status"),
        ("POST", "/api/web-research/enable"),
        ("POST", "/api/web-research/disable"),
        ("POST", "/api/web-research/test"),
        ("POST", "/api/web-research/clear-cache"),
        ("POST", "/api/web-research/reset-circuit-breakers"),
        ("GET", "/api/web-research/usage-stats"),
    ],
)
def test_researcher_endpoints_503_when_unavailable(method: str, path: str) -> None:
    """Startup init failure (state=None) yields an actionable 503, not a crash."""
    client = _client(researcher=None)

    response = client.request(method, path)

    assert response.status_code == 503
    assert response.json()["detail"] == _RESEARCHER_UNAVAILABLE_DETAIL


def test_status_200_when_researcher_available() -> None:
    """With an initialized researcher the status endpoint keeps working."""
    client = _client(researcher=_mock_researcher())

    response = client.get("/api/web-research/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["enabled"] is True
