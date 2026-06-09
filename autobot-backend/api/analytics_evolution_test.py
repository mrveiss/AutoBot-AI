# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for analytics_evolution.py source_id scoping (Issue #3436)

Tests the following functionality:
- _decode_redis_value helper function
- _parse_date_range helper function
- _no_data_response helper function
- _calculate_metric_trend helper function
- _resolve_source_or_404 guard logic (mocked via sys.modules)
"""

import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_shared_mock(return_path=None):
    """Build a fake api.codebase_analytics.endpoints.shared module."""

    async def fake_resolve(source_id):
        if source_id is None:
            return None
        return return_path

    mod = types.ModuleType("api.codebase_analytics.endpoints.shared")
    mod.resolve_source_root = fake_resolve
    return mod


class TestDecodeRedisValue:
    """Tests for _decode_redis_value utility function."""

    def test_decodes_bytes(self):
        """Bytes value should be decoded to string."""
        from api.analytics_evolution import _decode_redis_value

        assert _decode_redis_value(b"hello") == "hello"

    def test_passes_through_string(self):
        """String value should pass through unchanged."""
        from api.analytics_evolution import _decode_redis_value

        assert _decode_redis_value("world") == "world"


class TestParseDateRange:
    """Tests for _parse_date_range helper function."""

    def test_none_dates_produce_sensible_defaults(self):
        """None start/end should produce a ~30-day window ending now."""
        from api.analytics_evolution import _parse_date_range

        start_ts, end_ts = _parse_date_range(None, None)
        now = datetime.now().timestamp()

        assert abs(end_ts - now) < 5
        expected_start = (datetime.now() - timedelta(days=30)).timestamp()
        assert abs(start_ts - expected_start) < 5

    def test_explicit_dates_are_parsed(self):
        """ISO date strings should be parsed to timestamps."""
        from api.analytics_evolution import _parse_date_range

        start = "2025-01-01"
        end = "2025-01-31"
        start_ts, end_ts = _parse_date_range(start, end)

        expected_start = datetime.fromisoformat(start).timestamp()
        expected_end = datetime.fromisoformat(end).timestamp()
        assert start_ts == expected_start
        assert end_ts == expected_end


class TestNoDataResponse:
    """Tests for _no_data_response in analytics_evolution."""

    def test_default_response_structure(self):
        """Should include status, message, timeline, patterns, trends keys."""
        from api.analytics_evolution import _no_data_response

        result = _no_data_response()
        assert result["status"] == "no_data"
        assert "message" in result
        assert "timeline" in result
        assert "patterns" in result
        assert "trends" in result

    def test_custom_message(self):
        """Should accept custom message."""
        from api.analytics_evolution import _no_data_response

        result = _no_data_response("Custom evolution message")
        assert result["message"] == "Custom evolution message"


class TestCalculateMetricTrend:
    """Tests for _calculate_metric_trend helper."""

    def test_returns_none_when_insufficient_data(self):
        """Less than 2 data points should return None."""
        from api.analytics_evolution import _calculate_metric_trend

        snapshots = [{"overall_score": 80}]
        result = _calculate_metric_trend(snapshots, "overall_score")
        assert result is None

    def test_calculates_trend_for_improving_metric(self):
        """Positive change should show improving direction."""
        from api.analytics_evolution import _calculate_metric_trend

        snapshots = [
            {"overall_score": 70},
            {"overall_score": 80},
        ]
        result = _calculate_metric_trend(snapshots, "overall_score")
        assert result is not None
        assert result["direction"] == "improving"
        assert result["change"] == 10.0
        assert result["data_points"] == 2

    def test_calculates_trend_for_declining_metric(self):
        """Negative change should show declining direction."""
        from api.analytics_evolution import _calculate_metric_trend

        snapshots = [
            {"overall_score": 90},
            {"overall_score": 70},
        ]
        result = _calculate_metric_trend(snapshots, "overall_score")
        assert result is not None
        assert result["direction"] == "declining"

    def test_stable_metric_when_no_change(self):
        """Zero change should show stable direction."""
        from api.analytics_evolution import _calculate_metric_trend

        snapshots = [
            {"overall_score": 80},
            {"overall_score": 80},
        ]
        result = _calculate_metric_trend(snapshots, "overall_score")
        assert result is not None
        assert result["direction"] == "stable"


class TestSourceIdGuardLogic:
    """Tests for _resolve_source_or_404 guard (mocked via sys.modules injection)."""

    @pytest.mark.asyncio
    async def test_none_source_id_does_not_raise(self):
        """_resolve_source_or_404 with None should return without raising."""
        from api.analytics_evolution import _resolve_source_or_404

        await _resolve_source_or_404(None)

    @pytest.mark.asyncio
    async def test_unknown_source_id_raises_404(self):
        """_resolve_source_or_404 with unknown source_id should raise HTTP 404."""
        from fastapi import HTTPException

        fake_mod = _make_shared_mock(return_path=None)
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_evolution import _resolve_source_or_404

            with pytest.raises(HTTPException) as exc_info:
                await _resolve_source_or_404("nonexistent-id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_source_id_does_not_raise(self):
        """_resolve_source_or_404 with valid source_id should return without raising."""
        fake_mod = _make_shared_mock(return_path=Path("/repos/evolution-project"))
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_evolution import _resolve_source_or_404

            await _resolve_source_or_404("valid-id")
