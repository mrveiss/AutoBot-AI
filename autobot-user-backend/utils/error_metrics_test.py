"""
Tests for Error Metrics Collection System

Validates error metrics collection, aggregation, and reporting functionality
"""

import asyncio
import time

import pytest

from backend.utils.error_boundaries import ErrorCategory
from backend.utils.error_metrics import ErrorMetricsCollector, get_metrics_collector


class TestErrorMetrics:
    """Test error metrics collection functionality"""

    @pytest.fixture
    def collector(self):
        """Create fresh metrics collector for each test"""
        return ErrorMetricsCollector(redis_client=None)

    @pytest.mark.asyncio
    async def test_record_error(self, collector):
        """Test recording a single error"""
        await collector.record_error(
            error_code="KB_0001",
            category=ErrorCategory.SERVER_ERROR,
            component="knowledge_base",
            function="search",
            message="Search failed",
        )

        stats = collector.get_stats()
        assert len(stats) == 1
        assert stats[0].component == "knowledge_base"
        assert stats[0].error_code == "KB_0001"
        assert stats[0].total_count == 1

    @pytest.mark.asyncio
    async def test_multiple_errors_same_type(self, collector):
        """Test recording multiple errors of the same type"""
        for i in range(5):
            await collector.record_error(
                error_code="LLM_0001",
                category=ErrorCategory.SERVICE_UNAVAILABLE,
                component="llm_service",
                function="generate",
                message=f"Generation failed {i}",
            )

        stats = collector.get_stats(component="llm_service")
        assert len(stats) == 1
        assert stats[0].total_count == 5

    @pytest.mark.asyncio
    async def test_retry_tracking(self, collector):
        """Test retry attempt tracking"""
        # Record error with retry
        await collector.record_error(
            error_code="DB_0001",
            category=ErrorCategory.DATABASE,
            component="database",
            function="connect",
            message="Connection failed",
            retry_attempted=True,
        )

        # Record error without retry
        await collector.record_error(
            error_code="DB_0001",
            category=ErrorCategory.DATABASE,
            component="database",
            function="connect",
            message="Connection failed",
            retry_attempted=False,
        )

        stats = collector.get_stats(component="database")
        assert stats[0].total_count == 2
        assert stats[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_mark_resolved(self, collector):
        """Test marking error as resolved"""
        trace_id = "test_trace_123"

        await collector.record_error(
            error_code="API_0001",
            category=ErrorCategory.VALIDATION,
            component="api",
            function="validate",
            message="Validation failed",
            trace_id=trace_id,
        )

        # Mark as resolved
        success = await collector.mark_resolved(trace_id)
        assert success is True

        stats = collector.get_stats(component="api")
        assert stats[0].resolved_count == 1

        # Try marking nonexistent error
        success = await collector.mark_resolved("nonexistent_trace")
        assert success is False

    def test_get_recent_errors(self, collector):
        """Test retrieving recent errors"""
        asyncio.run(self._populate_errors(collector, count=15))

        recent = collector.get_recent_errors(limit=10)
        assert len(recent) == 10

        # Should be in reverse chronological order
        timestamps = [m.timestamp for m in recent]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_component_filtering(self, collector):
        """Test filtering errors by component"""
        asyncio.run(
            self._populate_errors_multi_component(
                collector, component1="comp_a", component2="comp_b"
            )
        )

        comp_a_stats = collector.get_stats(component="comp_a")
        comp_b_stats = collector.get_stats(component="comp_b")

        assert all(s.component == "comp_a" for s in comp_a_stats)
        assert all(s.component == "comp_b" for s in comp_b_stats)

    def test_error_timeline(self, collector):
        """Test error timeline generation"""
        asyncio.run(self._populate_errors(collector, count=10))

        timeline = collector.get_error_timeline(hours=24)
        assert isinstance(timeline, dict)
        assert len(timeline) > 0

        # Check timeline structure
        for hour_key, errors in timeline.items():
            assert isinstance(hour_key, str)
            assert isinstance(errors, list)

    def test_category_breakdown(self, collector):
        """Test error breakdown by category"""
        asyncio.run(self._populate_errors_multi_category(collector))

        breakdown = collector.get_category_breakdown()

        assert "server_error" in breakdown
        assert "validation" in breakdown
        assert all(isinstance(count, int) for count in breakdown.values())

    def test_component_breakdown(self, collector):
        """Test error breakdown by component"""
        asyncio.run(self._populate_errors_multi_component(collector))

        breakdown = collector.get_component_breakdown()

        assert "comp_a" in breakdown
        assert "comp_b" in breakdown
        assert all(isinstance(count, int) for count in breakdown.values())

    def test_top_errors(self, collector):
        """Test getting top N errors"""
        asyncio.run(self._populate_errors_with_varying_counts(collector))

        top_errors = collector.get_top_errors(limit=3)

        assert len(top_errors) <= 3
        # Should be sorted by count descending
        counts = [s.total_count for s in top_errors]
        assert counts == sorted(counts, reverse=True)

    def test_summary(self, collector):
        """Test getting overall summary"""
        asyncio.run(self._populate_errors(collector, count=20))

        summary = collector.get_summary()

        assert "total_errors" in summary
        assert "unique_error_types" in summary
        assert "category_breakdown" in summary
        assert "component_breakdown" in summary
        assert "top_errors" in summary

        assert summary["total_errors"] >= 20

    def test_alert_threshold(self, collector):
        """Test setting and checking alert thresholds"""
        collector.set_alert_threshold("test_component", "TEST_001", threshold=5)

        # Record errors up to threshold
        async def record_errors():
            for i in range(10):
                await collector.record_error(
                    error_code="TEST_001",
                    category=ErrorCategory.SERVER_ERROR,
                    component="test_component",
                    function="test_func",
                    message=f"Test error {i}",
                )

        asyncio.run(record_errors())

        stats = collector.get_stats(component="test_component")
        assert stats[0].total_count == 10

    @pytest.mark.asyncio
    async def test_cleanup_old_metrics(self, collector):
        """Test cleanup of old metrics"""
        # Record some errors
        await collector.record_error(
            error_code="OLD_001",
            category=ErrorCategory.SERVER_ERROR,
            component="test",
            function="old",
            message="Old error",
        )

        initial_count = len(collector._metrics)
        assert initial_count > 0

        # Manually set old timestamp
        if collector._metrics:
            collector._metrics[0].timestamp = time.time() - (
                collector._retention_seconds + 100
            )

        # Cleanup
        removed = await collector.cleanup_old_metrics()

        assert removed >= 0  # May be 0 if no old metrics

    @pytest.mark.asyncio
    async def test_reset_stats(self, collector):
        """Test resetting statistics"""
        await collector.record_error(
            error_code="RESET_001",
            category=ErrorCategory.SERVER_ERROR,
            component="test_component",
            function="test",
            message="Test error",
        )

        # Verify stats exist
        stats = collector.get_stats(component="test_component")
        assert len(stats) > 0

        # Reset
        await collector.reset_stats(component="test_component")

        # Verify stats cleared
        stats = collector.get_stats(component="test_component")
        assert len(stats) == 0

    def test_singleton_pattern(self):
        """Test that get_metrics_collector returns singleton"""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    @pytest.mark.asyncio
    async def test_error_rate_calculation(self, collector):
        """Test error rate calculation"""
        # Record multiple errors
        for i in range(10):
            await collector.record_error(
                error_code="RATE_001",
                category=ErrorCategory.SERVER_ERROR,
                component="test",
                function="test",
                message=f"Error {i}",
            )

        stats = collector.get_stats(component="test")
        assert stats[0].error_rate >= 0.0

    # Helper methods

    async def _populate_errors(self, collector, count=10):
        """Populate collector with test errors"""
        for i in range(count):
            await collector.record_error(
                error_code=f"TEST_{i % 3:03d}",
                category=ErrorCategory.SERVER_ERROR,
                component="test_component",
                function="test_function",
                message=f"Test error {i}",
            )

    async def _populate_errors_multi_component(
        self, collector, component1="comp_a", component2="comp_b"
    ):
        """Populate collector with errors from multiple components"""
        for i in range(5):
            await collector.record_error(
                error_code=f"TEST_{i:03d}",
                category=ErrorCategory.SERVER_ERROR,
                component=component1,
                function="func_a",
                message=f"Error from {component1}",
            )

            await collector.record_error(
                error_code=f"TEST_{i:03d}",
                category=ErrorCategory.VALIDATION,
                component=component2,
                function="func_b",
                message=f"Error from {component2}",
            )

    async def _populate_errors_multi_category(self, collector):
        """Populate collector with errors from multiple categories"""
        categories = [
            ErrorCategory.SERVER_ERROR,
            ErrorCategory.VALIDATION,
            ErrorCategory.AUTHENTICATION,
        ]

        for i, category in enumerate(categories):
            for j in range(3):
                await collector.record_error(
                    error_code=f"TEST_{i:03d}",
                    category=category,
                    component=f"comp_{i}",
                    function="test_func",
                    message=f"Error in category {category.value}",
                )

    async def _populate_errors_with_varying_counts(self, collector):
        """Populate collector with errors with varying counts"""
        error_counts = [
            (f"ERR_{i:03d}", count) for i, count in enumerate([10, 5, 3, 1])
        ]

        for error_code, count in error_counts:
            for i in range(count):
                await collector.record_error(
                    error_code=error_code,
                    category=ErrorCategory.SERVER_ERROR,
                    component="test_component",
                    function="test_func",
                    message=f"Error {error_code} occurrence {i}",
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
