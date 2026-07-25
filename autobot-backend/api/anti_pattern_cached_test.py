# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for GET /api/anti-pattern/cached graceful no_data handling (Issue #12365)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.anti_pattern as anti_pattern_module
from api.anti_pattern import router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/anti-pattern")
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


@pytest.fixture(autouse=True)
def _reset_detector_singleton():
    """_get_detector() memoizes into a module-global singleton; reset it around
    every test so a real-loaded detector from one test can't leak into the
    next (or vice versa: a mocked call leaving stale global state)."""
    anti_pattern_module._detector_instance = None
    yield
    anti_pattern_module._detector_instance = None


class TestGetDetectorRealLoad:
    """Issue #12365: _get_detector() previously loaded a deleted file path
    (tools/code-analysis-suite/src/anti_pattern_detector.py, removed by the
    #781/#926 restructuring per #12436) via importlib.spec_from_file_location,
    raising FileNotFoundError on every call -- every /api/anti-pattern/*
    endpoint was broken. It now imports the canonical
    code_analysis.src.anti_pattern_detector module directly."""

    @pytest.mark.asyncio
    async def test_resolves_without_file_not_found(self):
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            AsyncMock(return_value=None),
        ):
            detector = await anti_pattern_module._get_detector()

        from code_analysis.src.anti_pattern_detector import AntiPatternDetector

        assert isinstance(detector, AntiPatternDetector)

    @pytest.mark.asyncio
    async def test_wires_redis_client_for_caching(self):
        """The detector defaults redis_client=None, which makes its own
        _cache_results/get_cached_report no-ops -- /analyze would never
        actually populate the store /cached reads unless a real client is
        passed at construction."""
        sentinel_redis = object()
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            AsyncMock(return_value=sentinel_redis),
        ):
            detector = await anti_pattern_module._get_detector()

        assert detector.redis_client is sentinel_redis


class TestGetCachedAnalysis:
    def test_cache_miss_returns_no_data_not_404(self, client):
        """Empty cache (detector returns None) degrades to 200 no_data."""
        mock_detector = AsyncMock()
        mock_detector.get_cached_report.return_value = None

        with patch("api.anti_pattern._get_detector", AsyncMock(return_value=mock_detector)):
            resp = client.get("/api/anti-pattern/cached")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_data"

    def test_retrieval_exception_returns_no_data_not_500(self, client):
        """A cache READ error degrades to 200 no_data instead of 500."""
        mock_detector = AsyncMock()
        mock_detector.get_cached_report.side_effect = RuntimeError("redis unavailable")

        with patch("api.anti_pattern._get_detector", AsyncMock(return_value=mock_detector)):
            resp = client.get("/api/anti-pattern/cached")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_data"

    def test_detector_construction_fault_is_not_masked(self, client):
        """#12365 review item b: a broken detector (infra fault) must surface,
        not be reported as an empty cache. Only the cache READ degrades."""
        with patch(
            "api.anti_pattern._get_detector",
            AsyncMock(side_effect=RuntimeError("detector import failed")),
        ):
            resp = client.get("/api/anti-pattern/cached")

        # Whatever the error envelope, it must NOT be a 200 no_data.
        assert not (resp.status_code == 200 and resp.json().get("status") == "no_data")

    def test_cache_hit_returns_data(self, client):
        """Cached results still return normally when present."""
        mock_detector = AsyncMock()
        mock_detector.get_cached_report.return_value = {"total_issues": 3}

        with patch("api.anti_pattern._get_detector", AsyncMock(return_value=mock_detector)):
            resp = client.get("/api/anti-pattern/cached")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["cached"] is True
        assert body["data"] == {"total_issues": 3}
