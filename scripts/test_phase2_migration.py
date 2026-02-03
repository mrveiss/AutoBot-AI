#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script for Phase 2 Consumer Migration (Issue #345)

Validates that all migrated consumers are pushing to Prometheus.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.prometheus_metrics import get_metrics_manager
from src.utils.system_metrics import get_metrics_collector
from src.utils.error_metrics import get_metrics_collector as get_error_collector
from src.utils.error_boundaries import ErrorCategory
from src.monitoring.claude_api_monitor import ClaudeAPIMonitor


async def test_phase2_migration():
    """Test that Phase 2 migrations are working"""
    print("=" * 70)
    print("Testing Phase 2 Consumer Migration (Issue #345)")
    print("=" * 70)

    # Get metrics manager
    metrics_manager = get_metrics_manager()

    # Test 1: SystemMetricsCollector dual-write
    print("\n✓ Testing SystemMetricsCollector dual-write...")
    system_collector = get_metrics_collector()

    # Collect metrics (should push to Prometheus)
    await system_collector.collect_system_metrics()
    print("  ✓ System metrics collected and pushed to Prometheus")

    # Test 2: ErrorMetricsCollector dual-write
    print("\n✓ Testing ErrorMetricsCollector dual-write...")
    error_collector = get_error_collector()

    # Record an error (should push to Prometheus)
    await error_collector.record_error(
        error_code="TEST_ERROR",
        category=ErrorCategory.API,
        component="test_component",
        function="test_function",
        message="Test error for Phase 2 migration"
    )
    print("  ✓ Error recorded and pushed to Prometheus")

    # Test 3: ClaudeAPIMonitor dual-write
    print("\n✓ Testing ClaudeAPIMonitor dual-write...")
    claude_monitor = ClaudeAPIMonitor()

    # Record API call (should push to Prometheus)
    claude_monitor.record_api_call(
        payload_size=1024,
        response_size=512,
        response_time=0.5,
        success=True,
        tool_name="test_tool"
    )
    print("  ✓ Claude API call recorded and pushed to Prometheus")

    # Test 4: Verify metrics are in Prometheus output
    print("\n✓ Verifying metrics in Prometheus output...")
    metrics_output = metrics_manager.get_metrics().decode("utf-8")

    # Check for system metrics
    if "autobot_cpu_usage_percent" in metrics_output:
        print("  ✓ System metrics present in Prometheus output")
    else:
        print("  ✗ System metrics NOT FOUND")
        return False

    # Check for error metrics
    if "autobot_errors_total" in metrics_output:
        print("  ✓ Error metrics present in Prometheus output")
    else:
        print("  ✗ Error metrics NOT FOUND")
        return False

    # Check for Claude API metrics
    if "autobot_claude_api_requests_total" in metrics_output:
        print("  ✓ Claude API metrics present in Prometheus output")
    else:
        print("  ✗ Claude API metrics NOT FOUND")
        return False

    print("\n" + "=" * 70)
    print("✅ All Phase 2 migration tests PASSED!")
    print("=" * 70)
    print("\nAll migrated collectors are successfully dual-writing to Prometheus.")
    print("Metrics endpoint: http://172.16.168.20:8001/api/monitoring/metrics\n")

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_phase2_migration())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
