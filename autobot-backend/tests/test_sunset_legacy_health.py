# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Issue #6902: SunsetLegacyHealthMiddleware adds Sunset/Deprecation headers
to legacy /api/<module>/health routes — but NOT to the canonical aggregator
at /api/system/health.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.sunset_legacy_health import (
    SUNSET_DATE_HTTP,
    SunsetLegacyHealthMiddleware,
    _is_legacy_module_health,
)


def _build_app() -> TestClient:
    app = FastAPI()
    app.add_middleware(SunsetLegacyHealthMiddleware)

    @app.get("/api/system/health")
    async def canonical_health():
        return {"status": "healthy"}

    @app.get("/api/health")
    async def alias_health():
        return {"status": "healthy"}

    @app.get("/api/redis/health")
    async def legacy_redis_health():
        return {"status": "ok"}

    @app.get("/api/batch-jobs/health")
    async def legacy_batch_health():
        return {"status": "ok"}

    @app.get("/api/system/info")
    async def info():
        return {"version": "1.0"}

    @app.get("/api/quality/health-score")
    async def health_score():
        return {"score": 95}

    return TestClient(app)


def test_legacy_module_health_gets_sunset_header():
    client = _build_app()
    response = client.get("/api/redis/health")
    assert response.status_code == 200
    assert response.headers.get("Sunset") == SUNSET_DATE_HTTP
    assert response.headers.get("Deprecation") == "true"
    assert "/api/system/health" in response.headers.get("Link", "")
    assert 'rel="successor-version"' in response.headers.get("Link", "")


def test_canonical_aggregator_does_not_get_sunset_header():
    client = _build_app()
    response = client.get("/api/system/health")
    assert response.status_code == 200
    assert "Sunset" not in response.headers
    assert "Deprecation" not in response.headers
    assert "Link" not in response.headers


def test_legacy_alias_does_not_get_sunset_header():
    client = _build_app()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "Sunset" not in response.headers
    assert "Deprecation" not in response.headers


def test_unrelated_routes_do_not_get_sunset_header():
    client = _build_app()
    info_response = client.get("/api/system/info")
    assert "Sunset" not in info_response.headers
    score_response = client.get("/api/quality/health-score")
    assert "Sunset" not in score_response.headers


def test_legacy_with_hyphenated_module_name_matches():
    client = _build_app()
    response = client.get("/api/batch-jobs/health")
    assert response.headers.get("Sunset") == SUNSET_DATE_HTTP
    assert response.headers.get("Deprecation") == "true"


# --- _is_legacy_module_health predicate -------------------------------------


def test_is_legacy_match_simple_module():
    assert _is_legacy_module_health("/api/redis/health") is True
    assert _is_legacy_module_health("/api/batch-jobs/health") is True
    assert _is_legacy_module_health("/api/error_resilience/health") is True


def test_is_legacy_excludes_canonical_paths():
    assert _is_legacy_module_health("/api/system/health") is False
    assert _is_legacy_module_health("/api/health") is False


def test_is_legacy_excludes_non_health_paths():
    assert _is_legacy_module_health("/api/system/info") is False
    assert _is_legacy_module_health("/api/quality/health-score") is False
    assert _is_legacy_module_health("/api/knowledge-maintenance/health/dashboard") is False


def test_is_legacy_excludes_non_api_prefix():
    assert _is_legacy_module_health("/health") is False
    assert _is_legacy_module_health("/redis/health") is False
    assert _is_legacy_module_health("/static/health") is False
