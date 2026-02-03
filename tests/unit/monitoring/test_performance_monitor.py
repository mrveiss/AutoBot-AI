# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for PerformanceMonitor class.

Tests for Issue #427: Ensure PerformanceMonitor has all required attributes
for the monitoring API endpoints.
"""

import unittest
from unittest.mock import patch, MagicMock


class TestPerformanceMonitorInitialization(unittest.TestCase):
    """Test PerformanceMonitor initialization with required attributes."""

    @patch("src.utils.redis_client.get_redis_client")
    def test_gpu_metrics_buffer_initialized(self, mock_redis):
        """Test that gpu_metrics_buffer is initialized as empty list."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitoring.monitor import PerformanceMonitor

        monitor = PerformanceMonitor()
        self.assertIsInstance(monitor.gpu_metrics_buffer, list)
        self.assertEqual(len(monitor.gpu_metrics_buffer), 0)

    @patch("src.utils.redis_client.get_redis_client")
    def test_npu_metrics_buffer_initialized(self, mock_redis):
        """Test that npu_metrics_buffer is initialized as empty list."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitoring.monitor import PerformanceMonitor

        monitor = PerformanceMonitor()
        self.assertIsInstance(monitor.npu_metrics_buffer, list)
        self.assertEqual(len(monitor.npu_metrics_buffer), 0)

    @patch("src.utils.redis_client.get_redis_client")
    def test_multimodal_metrics_buffer_initialized(self, mock_redis):
        """Test that multimodal_metrics_buffer is initialized as empty list."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitoring.monitor import PerformanceMonitor

        monitor = PerformanceMonitor()
        self.assertIsInstance(monitor.multimodal_metrics_buffer, list)
        self.assertEqual(len(monitor.multimodal_metrics_buffer), 0)

    @patch("src.utils.redis_client.get_redis_client")
    def test_system_metrics_buffer_initialized(self, mock_redis):
        """Test that system_metrics_buffer is initialized as empty list."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitoring.monitor import PerformanceMonitor

        monitor = PerformanceMonitor()
        self.assertIsInstance(monitor.system_metrics_buffer, list)
        self.assertEqual(len(monitor.system_metrics_buffer), 0)

    @patch("src.utils.redis_client.get_redis_client")
    def test_performance_alerts_initialized(self, mock_redis):
        """Test that performance_alerts is initialized as empty list."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitoring.monitor import PerformanceMonitor

        monitor = PerformanceMonitor()
        self.assertIsInstance(monitor.performance_alerts, list)
        self.assertEqual(len(monitor.performance_alerts), 0)

    @patch("src.utils.redis_client.get_redis_client")
    def test_service_metrics_buffer_initialized(self, mock_redis):
        """Test that service_metrics_buffer is initialized as empty dict."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitoring.monitor import PerformanceMonitor

        monitor = PerformanceMonitor()
        self.assertIsInstance(monitor.service_metrics_buffer, dict)
        self.assertEqual(len(monitor.service_metrics_buffer), 0)

    @patch("src.utils.redis_client.get_redis_client")
    def test_all_monitoring_api_required_attributes(self, mock_redis):
        """Test all attributes required by /api/monitoring/status endpoint."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitoring.monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        # These are all required by backend/api/monitoring.py::get_monitoring_status()
        required_attrs = [
            "gpu_metrics_buffer",
            "npu_metrics_buffer",
            "multimodal_metrics_buffer",
            "system_metrics_buffer",
            "service_metrics_buffer",
            "performance_alerts",
            "monitoring_active",
            "collection_interval",
        ]

        for attr in required_attrs:
            self.assertTrue(
                hasattr(monitor, attr),
                f"PerformanceMonitor missing required attribute: {attr}",
            )

    @patch("src.utils.redis_client.get_redis_client")
    def test_performance_monitor_singleton_has_attributes(self, mock_redis):
        """Test that performance_monitor singleton has all required attributes."""
        mock_redis.return_value = MagicMock()
        from src.utils.performance_monitor import performance_monitor

        # Verify the singleton has all required attributes
        required_attrs = [
            "gpu_metrics_buffer",
            "npu_metrics_buffer",
            "multimodal_metrics_buffer",
            "system_metrics_buffer",
            "service_metrics_buffer",
            "performance_alerts",
        ]

        for attr in required_attrs:
            self.assertTrue(
                hasattr(performance_monitor, attr),
                f"performance_monitor missing required attribute: {attr}",
            )


if __name__ == "__main__":
    unittest.main()