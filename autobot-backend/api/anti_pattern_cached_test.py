# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for GET /api/anti-pattern/cached graceful no_data handling (Issue #12365)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.anti_pattern import router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/anti-pattern")
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


class TestGetCachedAnalysis:
    def test_cache_miss_returns_no_data_not_404(self, client):
        """Empty cache (detector returns None) degrades to 200 no_data."""
        mock_detector = AsyncMock()
        mock_detector.get_cached_report.return_value = None

        with patch("api.anti_pattern._get_detector", AsyncMock(return_value=mock_detector)):
            resp = client.get("/api/anti-pattern/cached")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["status"] == "no_data"

    def test_retrieval_exception_returns_no_data_not_500(self, client):
        """Cache retrieval error degrades to 200 no_data instead of 500."""
        mock_detector = AsyncMock()
        mock_detector.get_cached_report.side_effect = RuntimeError("redis unavailable")

        with patch("api.anti_pattern._get_detector", AsyncMock(return_value=mock_detector)):
            resp = client.get("/api/anti-pattern/cached")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["status"] == "no_data"

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
