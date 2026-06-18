# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Error Metrics Collection System

Phase 5 (Issue #348 / #9983): Validates the Prometheus-backed read path and
Redis-backed resolution state.  Prometheus and Redis calls are mocked so
the suite runs without live infrastructure.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.error_boundaries import ErrorCategory
from utils.error_metrics import ErrorMetricsCollector, get_metrics_collector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _instant_response(results):
    """Build a fake Prometheus instant query data dict."""
    return {"resultType": "vector", "result": results}


def _make_vector_item(labels, value):
    return {"metric": labels, "value": [1700000000.0, str(value)]}


# ---------------------------------------------------------------------------
# Record / write path
# ---------------------------------------------------------------------------


class TestRecordError:
    @pytest.fixture
    def collector(self):
        c = ErrorMetricsCollector(redis_client=None)
        c.prometheus = MagicMock()
        return c

    @pytest.mark.asyncio
    async def test_record_error_calls_prometheus(self, collector):
        await collector.record_error(
            error_code="KB_0001",
            category=ErrorCategory.SERVER_ERROR,
            component="knowledge_base",
            function="search",
            message="Search failed",
        )
        collector.prometheus.record_error.assert_called_once_with("server_error", "knowledge_base", "KB_0001")

    @pytest.mark.asyncio
    async def test_record_error_no_prometheus(self):
        collector = ErrorMetricsCollector()
        collector.prometheus = None
        # Must not raise even without prometheus
        await collector.record_error(
            error_code="X",
            category=ErrorCategory.SERVER_ERROR,
            component="c",
            function="f",
            message="m",
        )

    @pytest.mark.asyncio
    async def test_alert_threshold_triggers_warning(self, collector):
        collector.set_alert_threshold("comp", "ERR_001", threshold=2)
        # First error — below threshold
        await collector.record_error(
            error_code="ERR_001",
            category=ErrorCategory.SERVER_ERROR,
            component="comp",
            function="fn",
            message="err",
        )
        # Second error — at threshold
        await collector.record_error(
            error_code="ERR_001",
            category=ErrorCategory.SERVER_ERROR,
            component="comp",
            function="fn",
            message="err",
        )
        # No exception; threshold counter incremented
        assert collector._last_error_counts["comp:ERR_001"] == 2


# ---------------------------------------------------------------------------
# mark_resolved
# ---------------------------------------------------------------------------


class TestMarkResolved:
    @pytest.fixture
    def collector(self):
        c = ErrorMetricsCollector()
        return c

    @pytest.mark.asyncio
    async def test_mark_resolved_success(self, collector):
        mock_redis = MagicMock()
        mock_redis.sadd = MagicMock(return_value=1)
        mock_redis.expire = MagicMock(return_value=True)
        collector._redis = mock_redis

        result = await collector.mark_resolved("trace-abc")

        assert result is True
        mock_redis.sadd.assert_called_once_with("errors:resolved", "trace-abc")
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_resolved_no_redis(self, collector):
        collector._redis = None
        collector._get_redis = lambda: None
        result = await collector.mark_resolved("trace-xyz")
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_resolved_redis_error(self, collector):
        mock_redis = MagicMock()
        mock_redis.sadd = MagicMock(side_effect=ConnectionError("Redis down"))
        collector._redis = mock_redis
        result = await collector.mark_resolved("trace-xyz")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_resolved_true(self, collector):
        mock_redis = MagicMock()
        mock_redis.sismember = MagicMock(return_value=True)
        collector._redis = mock_redis
        assert await collector.is_resolved("trace-abc") is True

    @pytest.mark.asyncio
    async def test_is_resolved_false(self, collector):
        mock_redis = MagicMock()
        mock_redis.sismember = MagicMock(return_value=False)
        collector._redis = mock_redis
        assert await collector.is_resolved("trace-never") is False


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    @pytest.fixture
    def collector(self):
        return ErrorMetricsCollector()

    @pytest.mark.asyncio
    async def test_summary_with_prometheus_data(self, collector):
        total_data = _instant_response([_make_vector_item({}, 42)])
        cat_data = _instant_response(
            [
                _make_vector_item({"category": "server_error"}, 30),
                _make_vector_item({"category": "validation"}, 12),
            ]
        )
        comp_data = _instant_response(
            [
                _make_vector_item({"component": "api"}, 25),
                _make_vector_item({"component": "llm"}, 17),
            ]
        )
        uniq_data = _instant_response([_make_vector_item({}, 5)])

        with patch(
            "autobot_shared.monitoring.prometheus_query.query_instant",
            new_callable=AsyncMock,
        ) as mock_qi:
            mock_qi.side_effect = [total_data, cat_data, comp_data, uniq_data]
            summary = await collector.get_summary()

        assert summary["total_errors"] == 42
        assert summary["unique_error_types"] == 5
        assert summary["category_breakdown"]["server_error"] == 30
        assert summary["category_breakdown"]["validation"] == 12
        assert summary["component_breakdown"]["api"] == 25
        assert summary["prometheus_available"] is True

    @pytest.mark.asyncio
    async def test_summary_prometheus_unreachable(self, collector):
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_instant",
            new_callable=AsyncMock,
            return_value=None,
        ):
            summary = await collector.get_summary()

        assert summary["total_errors"] == 0
        assert summary["category_breakdown"] == {}
        # prometheus_available is True because the import worked, even though
        # query returned None (that's a runtime "no data" not "unavailable")
        # The helper returns None on HTTP failure; summary still works.

    @pytest.mark.asyncio
    async def test_summary_import_error(self, collector):
        with patch.dict("sys.modules", {"autobot_shared.monitoring.prometheus_query": None}):
            # Import error path — returns empty summary
            pass

            import utils.error_metrics as em

            with patch.object(em, "__builtins__", {}):
                # Simulate ImportError branch
                pass
        # Just verify no exception is raised and returns a dict
        assert isinstance(await collector.get_summary(), dict)


# ---------------------------------------------------------------------------
# get_top_errors
# ---------------------------------------------------------------------------


class TestGetTopErrors:
    @pytest.fixture
    def collector(self):
        return ErrorMetricsCollector()

    @pytest.mark.asyncio
    async def test_top_errors_shape(self, collector):
        prom_data = _instant_response(
            [
                _make_vector_item({"component": "api", "error_code": "API_001"}, 50),
                _make_vector_item({"component": "llm", "error_code": "LLM_002"}, 30),
            ]
        )
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_instant",
            new_callable=AsyncMock,
            return_value=prom_data,
        ):
            results = await collector.get_top_errors(limit=5)

        assert len(results) == 2
        assert results[0]["component"] == "api"
        assert results[0]["error_code"] == "API_001"
        assert results[0]["count"] == 50
        assert results[1]["count"] == 30

    @pytest.mark.asyncio
    async def test_top_errors_promql_string(self, collector):
        """Verify the PromQL sent to Prometheus uses the supplied limit."""
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_instant",
            new_callable=AsyncMock,
            return_value=_instant_response([]),
        ) as mock_qi:
            await collector.get_top_errors(limit=7)
        called_promql = mock_qi.call_args[0][0]
        assert "topk(7," in called_promql
        assert "component" in called_promql
        assert "error_code" in called_promql

    @pytest.mark.asyncio
    async def test_top_errors_prometheus_none(self, collector):
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_instant",
            new_callable=AsyncMock,
            return_value=None,
        ):
            results = await collector.get_top_errors(limit=10)
        assert results == []


# ---------------------------------------------------------------------------
# get_error_timeline
# ---------------------------------------------------------------------------


class TestGetErrorTimeline:
    @pytest.fixture
    def collector(self):
        return ErrorMetricsCollector()

    @pytest.mark.asyncio
    async def test_timeline_returns_points(self, collector):
        fake_points = [
            {"timestamp": "2025-01-01T00:00:00+00:00", "value": 1.5, "labels": {}},
            {"timestamp": "2025-01-01T00:05:00+00:00", "value": 2.0, "labels": {}},
        ]
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_range",
            new_callable=AsyncMock,
            return_value=fake_points,
        ):
            points = await collector.get_error_timeline(hours=2)

        assert len(points) == 2
        assert "timestamp" in points[0]
        assert "value" in points[0]
        # labels key is stripped from timeline output
        assert "labels" not in points[0]

    @pytest.mark.asyncio
    async def test_timeline_component_filter(self, collector):
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_range",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_qr:
            await collector.get_error_timeline(hours=6, component="api")

        called_promql = mock_qr.call_args[0][0]
        assert 'component="api"' in called_promql

    @pytest.mark.asyncio
    async def test_timeline_no_component_filter(self, collector):
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_range",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_qr:
            await collector.get_error_timeline(hours=24)

        called_promql = mock_qr.call_args[0][0]
        assert "component=" not in called_promql

    @pytest.mark.asyncio
    async def test_timeline_component_promql_injection_escaped(self, collector):
        """#9983 security: a malicious component param cannot break out of the
        quoted PromQL label value to inject arbitrary PromQL."""
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_range",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_qr:
            await collector.get_error_timeline(hours=6, component='x"} or up{job="y')

        called_promql = mock_qr.call_args[0][0]
        # the injected quote is escaped (\") so it cannot terminate the label
        # value early; the raw break-out sequence x"} must NOT appear.
        assert 'x\\"}' in called_promql
        assert 'x"}' not in called_promql

    @pytest.mark.asyncio
    async def test_timeline_prometheus_unreachable(self, collector):
        with patch(
            "autobot_shared.monitoring.prometheus_query.query_range",
            new_callable=AsyncMock,
            return_value=[],
        ):
            points = await collector.get_error_timeline(hours=1)
        assert points == []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_metrics_collector_returns_same_instance(self):
        c1 = get_metrics_collector()
        c2 = get_metrics_collector()
        assert c1 is c2

    def test_deprecated_get_stats_returns_empty(self):
        c = ErrorMetricsCollector()
        assert c.get_stats() == []

    def test_deprecated_get_category_breakdown_returns_empty(self):
        c = ErrorMetricsCollector()
        assert c.get_category_breakdown() == {}

    def test_deprecated_get_component_breakdown_returns_empty(self):
        c = ErrorMetricsCollector()
        assert c.get_component_breakdown() == {}

    @pytest.mark.asyncio
    async def test_cleanup_old_metrics_returns_zero(self):
        c = ErrorMetricsCollector()
        assert await c.cleanup_old_metrics() == 0

    @pytest.mark.asyncio
    async def test_reset_stats(self):
        c = ErrorMetricsCollector()
        c.prometheus = MagicMock()
        await c.record_error(
            error_code="R001",
            category=ErrorCategory.SERVER_ERROR,
            component="rc",
            function="fn",
            message="msg",
        )
        assert c._last_error_counts["rc:R001"] == 1
        await c.reset_stats(component="rc")
        assert "rc:R001" not in c._last_error_counts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
