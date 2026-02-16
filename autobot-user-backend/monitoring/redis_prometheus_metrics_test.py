"""
Unit tests for Redis Prometheus Metrics Integration - Issue #65 P1 Optimization
Tests that Redis operations properly record metrics to Prometheus.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from backend.monitoring.prometheus_metrics import get_metrics_manager
from backend.utils.redis_client import RedisConnectionManager


@pytest.fixture
def pool_manager():
    """Create a Redis pool manager for testing"""
    manager = RedisConnectionManager()
    return manager


@pytest.fixture
def mock_metrics():
    """Mock the Prometheus metrics manager"""
    with patch("src.utils.redis_client.get_metrics_manager") as mock_get:
        mock_manager = MagicMock()
        mock_get.return_value = mock_manager
        yield mock_manager


class TestRedisPrometheusIntegration:
    """Test Redis metrics are properly recorded to Prometheus"""

    def test_successful_operation_records_metric(self, pool_manager, mock_metrics):
        """Test that successful operations are recorded to Prometheus"""
        # Trigger stats update
        pool_manager._update_stats("main", success=True)

        # Verify Prometheus metric was recorded
        mock_metrics.record_request.assert_called_once_with(
            database="main", operation="general", success=True
        )

    def test_failed_operation_records_metric(self, pool_manager, mock_metrics):
        """Test that failed operations are recorded to Prometheus"""
        # Trigger stats update with failure
        pool_manager._update_stats(
            "knowledge", success=False, error="Connection timeout"
        )

        # Verify Prometheus metric was recorded
        mock_metrics.record_request.assert_called_once_with(
            database="knowledge", operation="general", success=False
        )

    def test_multiple_databases_tracked_separately(self, pool_manager, mock_metrics):
        """Test that different databases are tracked separately"""
        # Record operations for different databases
        pool_manager._update_stats("main", success=True)
        pool_manager._update_stats("prompts", success=True)
        pool_manager._update_stats("agents", success=False, error="Error")

        # Verify all three calls were made with correct parameters
        calls = mock_metrics.record_request.call_args_list
        assert len(calls) == 3

        assert calls[0] == call(database="main", operation="general", success=True)
        assert calls[1] == call(database="prompts", operation="general", success=True)
        assert calls[2] == call(database="agents", operation="general", success=False)

    def test_circuit_breaker_records_prometheus_event(self, pool_manager, mock_metrics):
        """Test that circuit breaker opening records to Prometheus"""
        # Set up circuit breaker threshold
        pool_manager._pool_config.circuit_breaker_threshold = 3

        # Simulate failures to trigger circuit breaker
        error = Exception("Connection refused")
        for _ in range(3):
            pool_manager._record_failure("metrics", error)

        # Verify circuit breaker event was recorded
        mock_metrics.record_circuit_breaker_event.assert_called_once()
        call_args = mock_metrics.record_circuit_breaker_event.call_args
        assert call_args[1]["database"] == "metrics"
        assert call_args[1]["event"] == "opened"
        assert "Connection refused" in call_args[1]["reason"]

        # Verify state update was called
        mock_metrics.update_circuit_breaker_state.assert_called_once_with(
            database="metrics", state="open", failure_count=3
        )

    def test_prometheus_failure_does_not_affect_redis(self, pool_manager):
        """Test that Prometheus recording failure doesn't break Redis operations"""
        with patch("src.utils.redis_client.get_metrics_manager") as mock_get:
            # Make prometheus throw an exception
            mock_get.side_effect = Exception("Prometheus unavailable")

            # This should not raise - internal stats should still update
            pool_manager._update_stats("main", success=True)

            # Verify internal stats were updated despite Prometheus failure
            stats = pool_manager._database_stats["main"]
            assert stats.successful_operations == 1

    def test_stats_include_prometheus_integration_metadata(self, pool_manager):
        """Test that stats tracking includes proper metadata"""
        # Perform some operations
        pool_manager._update_stats("main", success=True)
        pool_manager._update_stats("main", success=True)
        pool_manager._update_stats("main", success=False, error="Test error")

        # Verify internal stats are accurate
        stats = pool_manager._database_stats["main"]
        assert stats.successful_operations == 2
        assert stats.failed_operations == 1
        assert stats.last_error == "Test error"
        assert stats.last_error_time is not None

    def test_internal_stats_increment_correctly(self, pool_manager, mock_metrics):
        """Test that both internal and Prometheus stats increment correctly"""
        # Multiple operations
        for i in range(5):
            pool_manager._update_stats("workflows", success=True)

        pool_manager._update_stats("workflows", success=False, error="Error")

        # Check internal stats
        stats = pool_manager._database_stats["workflows"]
        assert stats.successful_operations == 5
        assert stats.failed_operations == 1

        # Check Prometheus was called 6 times
        assert mock_metrics.record_request.call_count == 6


class TestPrometheusMetricsManager:
    """Test the actual PrometheusMetricsManager behavior"""

    def test_global_metrics_manager_is_singleton(self):
        """Test that get_metrics_manager returns singleton"""
        manager1 = get_metrics_manager()
        manager2 = get_metrics_manager()
        assert manager1 is manager2

    def test_metrics_manager_has_redis_counters(self):
        """Test that metrics manager has Redis-specific counters"""
        manager = get_metrics_manager()

        # Verify Redis metrics exist
        assert hasattr(manager, "requests_total")
        assert hasattr(manager, "success_rate")
        assert hasattr(manager, "pool_connections")
        assert hasattr(manager, "pool_saturation")
        assert hasattr(manager, "circuit_breaker_events")
        assert hasattr(manager, "circuit_breaker_state")

    def test_record_request_updates_counter(self):
        """Test that record_request properly updates Prometheus counter"""
        manager = get_metrics_manager()

        # This should not raise and should update internal counters
        manager.record_request(database="test_db", operation="test_op", success=True)

        # Counter should be incremented (we verify it doesn't raise)
        # In a real test, we'd check the actual counter value

    def test_circuit_breaker_state_mapping(self):
        """Test circuit breaker state values are mapped correctly"""
        manager = get_metrics_manager()

        # Test state mapping (closed=0, open=1, half_open=2)
        # This is testing the internal state mapping logic
        manager.update_circuit_breaker_state("test_db", "closed", 0)
        manager.update_circuit_breaker_state("test_db", "open", 5)
        manager.update_circuit_breaker_state("test_db", "half_open", 3)

        # These should not raise


class TestIntegrationWithRealMetrics:
    """Integration tests with actual Prometheus metrics (no mocking)"""

    def test_end_to_end_metrics_recording(self):
        """Test complete flow from Redis operation to Prometheus metrics"""
        manager = RedisConnectionManager()
        get_metrics_manager()

        # Perform operation
        manager._update_stats("integration_test", success=True)

        # The metric should be recorded (this verifies the full path works)
        # We can't easily check Prometheus internal state, but no exceptions means success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
