# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Issue #6902: SunsetLegacyHealthMiddleware adds Sunset/Deprecation headers
to legacy /api/<module>/health routes — but NOT to the canonical aggregator
at /api/system/health.

Issue #6919: middleware also emits an INFO log and increments
autobot_legacy_health_hits_total{path, user_agent} on every legacy hit.
"""

import logging
from unittest.mock import MagicMock, patch

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


# --- Telemetry signals (#6919) -----------------------------------------------


def test_legacy_hit_emits_info_log(caplog):
    client = _build_app()
    with caplog.at_level(logging.INFO, logger="middleware.sunset_legacy_health"):
        client.get("/api/redis/health")
    legacy_records = [r for r in caplog.records if "Legacy health hit" in r.message]
    assert len(legacy_records) == 1
    assert "/api/redis/health" in legacy_records[0].message


def test_canonical_path_does_not_emit_info_log(caplog):
    client = _build_app()
    with caplog.at_level(logging.INFO, logger="middleware.sunset_legacy_health"):
        client.get("/api/system/health")
    legacy_records = [r for r in caplog.records if "Legacy health hit" in r.message]
    assert len(legacy_records) == 0


def test_legacy_hit_increments_counter():
    import middleware.sunset_legacy_health as mw

    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels

    client = _build_app()
    with patch.object(mw, "autobot_legacy_health_hits_total", mock_counter):
        client.get("/api/redis/health", headers={"User-Agent": "prometheus/2.x"})

    mock_counter.labels.assert_called_once_with(path="/api/redis/health", user_agent="prometheus/2.x")
    mock_labels.inc.assert_called_once()


def test_canonical_path_does_not_increment_counter():
    import middleware.sunset_legacy_health as mw

    mock_counter = MagicMock()
    client = _build_app()
    with patch.object(mw, "autobot_legacy_health_hits_total", mock_counter):
        client.get("/api/system/health")

    mock_counter.labels.assert_not_called()


def test_user_agent_truncated_to_120_chars():
    import middleware.sunset_legacy_health as mw

    mock_counter = MagicMock()
    mock_counter.labels.return_value = MagicMock()

    client = _build_app()
    with patch.object(mw, "autobot_legacy_health_hits_total", mock_counter):
        client.get("/api/redis/health", headers={"User-Agent": "A" * 200})

    call_kwargs = mock_counter.labels.call_args.kwargs
    assert len(call_kwargs["user_agent"]) == 120


def test_missing_user_agent_defaults_to_unknown():
    import middleware.sunset_legacy_health as mw

    mock_counter = MagicMock()
    mock_counter.labels.return_value = MagicMock()

    client = _build_app()
    with patch.object(mw, "autobot_legacy_health_hits_total", mock_counter):
        client.get("/api/redis/health", headers={})

    call_kwargs = mock_counter.labels.call_args.kwargs
    assert call_kwargs["user_agent"] == "unknown"
