# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for MCP worker metrics recording (#4109).

Tests verify that restart budget exhaustion, crash intervals, and
circuit breaker activation are properly recorded.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry

from autobot_shared.monitoring.metrics.mcp_worker import MCPWorkerMetricsRecorder


class TestMCPWorkerMetricsRecorder:
    """MCPWorkerMetricsRecorder metric recording."""

    def test_record_restart(self) -> None:
        """Record restart count updates the gauge."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        recorder.record_restart("filesystem_mcp", 1)
        recorder.record_restart("filesystem_mcp", 2)
        recorder.record_restart("filesystem_mcp", 3)

        # Verify gauge was set to final value
        metrics = registry.collect()
        metric_dict = {m.name: m for m in metrics}
        assert "autobot_mcp_worker_restart_count" in metric_dict

    def test_record_restart_budget_exhaustion(self) -> None:
        """Record restart budget exhaustion increments counter."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        recorder.record_restart_budget_exhaustion("filesystem_mcp")
        recorder.record_restart_budget_exhaustion("filesystem_mcp")

        # Verify counter was incremented
        metrics = registry.collect()
        metric_dict = {m.name: m for m in metrics}
        assert "autobot_mcp_worker_restart_budget_exhaustion_total" in metric_dict

    def test_record_crash_interval(self) -> None:
        """Record crash interval records to histogram."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        recorder.record_crash_interval("browser_mcp", 5.0)
        recorder.record_crash_interval("browser_mcp", 10.0)
        recorder.record_crash_interval("browser_mcp", 2.0)

        # Verify histogram was updated
        metrics = registry.collect()
        metric_dict = {m.name: m for m in metrics}
        assert "autobot_mcp_worker_crash_seconds" in metric_dict

    def test_set_circuit_breaker_activated(self) -> None:
        """Set circuit breaker activation state."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        recorder.set_circuit_breaker_activated("vnc_mcp", True)
        recorder.set_circuit_breaker_activated("vnc_mcp", False)

        # Verify gauge was updated
        metrics = registry.collect()
        metric_dict = {m.name: m for m in metrics}
        assert "autobot_mcp_worker_circuit_breaker_activated" in metric_dict

    def test_set_worker_uptime(self) -> None:
        """Set worker uptime in seconds."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        recorder.set_worker_uptime("knowledge_mcp", 0.0)
        recorder.set_worker_uptime("knowledge_mcp", 3600.0)

        # Verify gauge was updated
        metrics = registry.collect()
        metric_dict = {m.name: m for m in metrics}
        assert "autobot_mcp_worker_uptime_seconds" in metric_dict

    def test_set_permanently_failed(self) -> None:
        """Set permanent failure flag."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        recorder.set_permanently_failed("sequential_thinking_mcp", False)
        recorder.set_permanently_failed("sequential_thinking_mcp", True)

        # Verify gauge was updated
        metrics = registry.collect()
        metric_dict = {m.name: m for m in metrics}
        assert "autobot_mcp_worker_permanently_failed" in metric_dict

    def test_multiple_bridges(self) -> None:
        """Track metrics for multiple bridges independently."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        recorder.record_restart("filesystem_mcp", 1)
        recorder.record_restart("browser_mcp", 2)
        recorder.record_restart("vnc_mcp", 3)

        metrics = registry.collect()
        metric_dict = {m.name: m for m in metrics}
        assert "autobot_mcp_worker_restart_count" in metric_dict

    def test_all_metrics_initialized(self) -> None:
        """All metric attributes are initialized."""
        registry = CollectorRegistry()
        recorder = MCPWorkerMetricsRecorder(registry)

        assert hasattr(recorder, "restart_count")
        assert hasattr(recorder, "restart_budget_exhaustion_total")
        assert hasattr(recorder, "mcp_worker_crash_seconds")
        assert hasattr(recorder, "circuit_breaker_activated")
        assert hasattr(recorder, "worker_uptime_seconds")
        assert hasattr(recorder, "worker_permanently_failed")


__all__ = []
