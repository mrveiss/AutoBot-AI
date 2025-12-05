#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script for Phase 1 Prometheus metrics (Issue #344)

Validates that all new metrics are properly exposed.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.prometheus_metrics import get_metrics_manager
from src.monitoring.metrics_adapter import get_metrics_adapter


def test_prometheus_metrics():
    """Test that all Phase 1 metrics are properly initialized"""
    print("=" * 70)
    print("Testing Phase 1 Prometheus Metrics (Issue #344)")
    print("=" * 70)

    metrics_manager = get_metrics_manager()

    # Test that all new metrics exist
    print("\n✓ Checking System Metrics...")
    assert hasattr(metrics_manager, "system_cpu_usage"), "Missing system_cpu_usage"
    assert hasattr(metrics_manager, "system_memory_usage"), "Missing system_memory_usage"
    assert hasattr(metrics_manager, "system_disk_usage"), "Missing system_disk_usage"
    assert hasattr(
        metrics_manager, "system_network_bytes"
    ), "Missing system_network_bytes"
    print("  ✓ All system metrics initialized")

    print("\n✓ Checking Error Metrics...")
    assert hasattr(metrics_manager, "errors_total"), "Missing errors_total"
    assert hasattr(metrics_manager, "error_rate"), "Missing error_rate"
    print("  ✓ All error metrics initialized")

    print("\n✓ Checking Claude API Metrics...")
    assert hasattr(
        metrics_manager, "claude_api_requests_total"
    ), "Missing claude_api_requests_total"
    assert hasattr(
        metrics_manager, "claude_api_payload_bytes"
    ), "Missing claude_api_payload_bytes"
    assert hasattr(
        metrics_manager, "claude_api_response_time"
    ), "Missing claude_api_response_time"
    assert hasattr(
        metrics_manager, "claude_api_rate_limit_remaining"
    ), "Missing claude_api_rate_limit_remaining"
    print("  ✓ All Claude API metrics initialized")

    print("\n✓ Checking Service Health Metrics...")
    assert hasattr(
        metrics_manager, "service_health_score"
    ), "Missing service_health_score"
    assert hasattr(
        metrics_manager, "service_response_time"
    ), "Missing service_response_time"
    assert hasattr(metrics_manager, "service_status"), "Missing service_status"
    print("  ✓ All service health metrics initialized")

    # Test recording methods
    print("\n✓ Testing metric recording methods...")
    metrics_manager.update_system_cpu(45.5)
    metrics_manager.update_system_memory(62.3)
    metrics_manager.update_system_disk("/", 35.2)
    metrics_manager.record_network_bytes("sent", 1024)
    metrics_manager.record_error("api", "backend", "500")
    metrics_manager.update_error_rate("backend", "5m", 0.05)
    metrics_manager.record_claude_api_request("read", True)
    metrics_manager.record_claude_api_payload(2048)
    metrics_manager.record_claude_api_response_time(1.23)
    metrics_manager.update_claude_api_rate_limit(4950)
    metrics_manager.update_service_health("backend", 95.0)
    metrics_manager.record_service_response_time("redis", 0.015)
    metrics_manager.update_service_status("ollama", "online")
    print("  ✓ All recording methods work")

    # Test metrics output
    print("\n✓ Testing metrics output...")
    metrics_output = metrics_manager.get_metrics().decode("utf-8")

    # Check that new metrics appear in output
    expected_metrics = [
        "autobot_cpu_usage_percent",
        "autobot_memory_usage_percent",
        "autobot_disk_usage_percent",
        "autobot_network_bytes_total",
        "autobot_errors_total",
        "autobot_error_rate",
        "autobot_claude_api_requests_total",
        "autobot_claude_api_payload_bytes",
        "autobot_claude_api_response_time_seconds",
        "autobot_claude_api_rate_limit_remaining",
        "autobot_service_health_score",
        "autobot_service_response_time_seconds",
        "autobot_service_status",
    ]

    for metric in expected_metrics:
        if metric in metrics_output:
            print(f"  ✓ {metric}")
        else:
            print(f"  ✗ {metric} NOT FOUND")
            return False

    print("\n✓ Testing MetricsAdapter...")
    adapter = get_metrics_adapter()
    adapter.record_system_cpu(50.0)
    adapter.record_error("test", "test_component", "TEST_ERROR")
    adapter.record_claude_api_request("test_tool", True, 1024)
    print("  ✓ MetricsAdapter works (dual-write)")

    print("\n" + "=" * 70)
    print("✅ All Phase 1 metrics tests PASSED!")
    print("=" * 70)
    print("\nMetrics endpoint ready at: http://172.16.168.20:8001/api/monitoring/metrics")
    print("Configure Prometheus to scrape this endpoint.\n")

    return True


if __name__ == "__main__":
    try:
        success = test_prometheus_metrics()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
