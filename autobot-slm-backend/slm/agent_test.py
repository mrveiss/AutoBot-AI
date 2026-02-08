# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM node agent."""

from unittest.mock import MagicMock, patch

from slm.agent.health_collector import HealthCollector


class TestHealthCollector:
    """Test health data collection."""

    def test_collect_basic_health(self):
        """Test collecting basic health metrics."""
        collector = HealthCollector()
        health = collector.collect()

        assert "timestamp" in health
        assert "hostname" in health
        assert "cpu_percent" in health
        assert "memory_percent" in health
        assert "disk_percent" in health

    def test_check_service_status(self):
        """Test checking systemd service status."""
        collector = HealthCollector()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="active")
            status = collector.check_service("redis-stack-server")
            assert status["active"] is True

    def test_check_port_open(self):
        """Test port connectivity check."""
        collector = HealthCollector()

        with patch("socket.socket") as mock_socket:
            mock_instance = MagicMock()
            mock_socket.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_socket.return_value.__exit__ = MagicMock(return_value=False)
            mock_instance.connect_ex.return_value = 0

            is_open = collector.check_port("localhost", 6379)
            assert is_open is True

    def test_collect_includes_services(self):
        """Test health includes service checks."""
        collector = HealthCollector(services=["redis-stack-server"])

        with patch.object(collector, "check_service") as mock_check:
            mock_check.return_value = {"active": True, "status": "running"}
            health = collector.collect()

            assert "services" in health
            assert "redis-stack-server" in health["services"]
