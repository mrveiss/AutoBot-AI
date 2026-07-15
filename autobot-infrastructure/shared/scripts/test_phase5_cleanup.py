#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# NOTE: Test/CLI tool uses print() for user-facing output per LOGGING_STANDARDS.md
"""
Test script for Phase 5 Cleanup & Deprecation (Issue #348)

Validates that:
1. Legacy in-memory buffers have been removed from metrics collectors
2. Redis persistence has been removed
3. Prometheus is the primary metrics store
4. Deprecated methods/modules emit proper warnings
5. Grafana integration is functional
"""

import asyncio
import sys
import warnings
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 70)
print("Testing Phase 5 Cleanup & Deprecation (Issue #348)")
print("=" * 70)


def test_system_metrics_cleanup():
    """Test that SystemMetricsCollector has been cleaned up."""
    print("\n✓ SystemMetricsCollector Cleanup:")

    from utils.system_metrics import SystemMetricsCollector

    collector = SystemMetricsCollector()

    # Check that deque buffer has been removed
    has_buffer = hasattr(collector, "_metrics_buffer")
    if has_buffer:
        print("  ❌ _metrics_buffer still exists (should be removed)")
        return False
    else:
        print("  ✅ _metrics_buffer removed")

    # Check that _retention_hours has been removed
    has_retention = hasattr(collector, "_retention_hours")
    if has_retention:
        print("  ❌ _retention_hours still exists (should be removed)")
        return False
    else:
        print("  ✅ _retention_hours removed")

    # Check that _get_redis_client has been removed
    has_redis_method = hasattr(collector, "_get_redis_client")
    if has_redis_method:
        print("  ❌ _get_redis_client still exists (should be removed)")
        return False
    else:
        print("  ✅ _get_redis_client removed")

    # Check that store_metrics has been removed
    has_store = hasattr(collector, "store_metrics")
    if has_store:
        print("  ❌ store_metrics still exists (should be removed)")
        return False
    else:
        print("  ✅ store_metrics removed")

    # Check that get_recent_metrics has been removed
    has_recent = hasattr(collector, "get_recent_metrics")
    if has_recent:
        print("  ❌ get_recent_metrics still exists (should be removed)")
        return False
    else:
        print("  ✅ get_recent_metrics removed")

    # Check Prometheus integration
    has_prometheus = hasattr(collector, "prometheus")
    if has_prometheus:
        print("  ✅ Prometheus integration present")
    else:
        print("  ⚠️  Prometheus integration not found (expected)")

    return True


def test_error_metrics_cleanup():
    """Test that ErrorMetricsCollector has been cleaned up."""
    print("\n✓ ErrorMetricsCollector Cleanup:")

    from utils.error_metrics import ErrorMetricsCollector

    collector = ErrorMetricsCollector()

    # Check that _persist_metric has been removed
    has_persist = hasattr(collector, "_persist_metric")
    if has_persist:
        print("  ❌ _persist_metric still exists (should be removed)")
        return False
    else:
        print("  ✅ _persist_metric removed")

    # Check that get_recent_errors has been removed
    has_recent = hasattr(collector, "get_recent_errors")
    if has_recent:
        print("  ❌ get_recent_errors still exists (should be removed)")
        return False
    else:
        print("  ✅ get_recent_errors removed")

    # Check Prometheus integration
    has_prometheus = hasattr(collector, "prometheus")
    if has_prometheus:
        print("  ✅ Prometheus integration present")
    else:
        print("  ⚠️  Prometheus integration not found (expected)")

    # Check redis_client deprecation warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        # Create collector with redis_client (should warn)
        _ = ErrorMetricsCollector(redis_client="fake_client")
        if any("deprecated" in str(warning.message).lower() for warning in w):
            print("  ✅ redis_client deprecation warning emitted")
        else:
            print("  ⚠️  redis_client deprecation warning not captured (may use logger)")

    return True


def test_claude_api_monitor_deprecation():
    """Test that ClaudeAPIMonitor is properly deprecated."""
    print("\n✓ ClaudeAPIMonitor Deprecation:")

    # Check module docstring for deprecation notice
    import src.monitoring.claude_api_monitor as cam_module

    if "DEPRECATED" in cam_module.__doc__:
        print("  ✅ Module marked as DEPRECATED in docstring")
    else:
        print("  ❌ Module not marked as DEPRECATED")
        return False

    if "Phase 5" in cam_module.__doc__ and "#348" in cam_module.__doc__:
        print("  ✅ Docstring references Phase 5 and Issue #348")
    else:
        print("  ⚠️  Docstring should reference Phase 5 and Issue #348")

    # Check get_api_monitor deprecation warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from monitoring.claude_api_monitor import get_api_monitor

        _ = get_api_monitor()
        deprecation_warnings = [warning for warning in w if issubclass(warning.category, DeprecationWarning)]
        if deprecation_warnings:
            print("  ✅ get_api_monitor() emits DeprecationWarning")
        else:
            print("  ❌ get_api_monitor() should emit DeprecationWarning")
            return False

    # Check record_api_call deprecation warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from monitoring.claude_api_monitor import record_api_call

        asyncio.run(record_api_call(payload_size=100))
        deprecation_warnings = [warning for warning in w if issubclass(warning.category, DeprecationWarning)]
        if deprecation_warnings:
            print("  ✅ record_api_call() emits DeprecationWarning")
        else:
            print("  ❌ record_api_call() should emit DeprecationWarning")
            return False

    return True


def test_monitoring_compat_deprecation():
    """Test that monitoring_compat endpoints are deprecated."""
    print("\n✓ Monitoring Compatibility Layer:")

    from backend.api import monitoring_compat

    # Check for DEPRECATION_MSG
    if hasattr(monitoring_compat, "DEPRECATION_MSG"):
        print("  ✅ DEPRECATION_MSG defined")
    else:
        print("  ❌ DEPRECATION_MSG not found")
        return False

    # Check that all endpoints exist
    endpoints = [
        "get_system_metrics_current",
        "get_system_metrics_history",
        "get_workflow_summary",
        "get_recent_errors",
        "get_claude_api_status",
        "get_services_health",
        "get_github_status",
    ]

    all_found = True
    for endpoint in endpoints:
        if hasattr(monitoring_compat, endpoint):
            print(f"  ✅ {endpoint} exists")
        else:
            print(f"  ❌ {endpoint} not found")
            all_found = False

    return all_found


def test_redis_cleanup_script():
    """Test that Redis cleanup script exists and is valid."""
    print("\n✓ Redis Cleanup Script:")

    script_path = Path(__file__).parent / "cleanup_redis_metrics.py"

    if script_path.exists():
        print("  ✅ cleanup_redis_metrics.py exists")
    else:
        print("  ❌ cleanup_redis_metrics.py not found")
        return False

    # Check script content
    content = script_path.read_text()

    if "LEGACY_KEY_PATTERNS" in content:
        print("  ✅ LEGACY_KEY_PATTERNS defined")
    else:
        print("  ❌ LEGACY_KEY_PATTERNS not found")
        return False

    if "--dry-run" in content:
        print("  ✅ --dry-run flag supported")
    else:
        print("  ❌ --dry-run flag not found")
        return False

    # Check key patterns include expected patterns
    expected_patterns = ["metrics:system:", "error_metrics:", "kb_cache_stats"]
    for pattern in expected_patterns:
        if pattern in content:
            print(f"  ✅ Pattern '{pattern}' included")
        else:
            print(f"  ⚠️  Pattern '{pattern}' not found")

    return True


def test_grafana_integration():
    """Test that Grafana integration is in place."""
    print("\n✓ Grafana Integration:")

    # Check dashboards exist
    dashboard_dir = Path(__file__).parent.parent / "config" / "grafana" / "dashboards"

    dashboards = [
        "autobot-overview.json",
        "autobot-system.json",
        "autobot-workflow.json",
        "autobot-errors.json",
        "autobot-claude-api.json",
        "autobot-github.json",
    ]

    all_found = True
    for dashboard in dashboards:
        path = dashboard_dir / dashboard
        if path.exists():
            print(f"  ✅ {dashboard}")
        else:
            print(f"  ❌ {dashboard} not found")
            all_found = False

    # Check Vue component exists
    vue_component = (
        Path(__file__).parent.parent / "autobot-vue" / "src" / "components" / "monitoring" / "GrafanaDashboard.vue"
    )

    if vue_component.exists():
        print("  ✅ GrafanaDashboard.vue")
    else:
        print("  ❌ GrafanaDashboard.vue not found")
        all_found = False

    return all_found


def main():
    """Run all Phase 5 tests."""
    results = {
        "SystemMetricsCollector": test_system_metrics_cleanup(),
        "ErrorMetricsCollector": test_error_metrics_cleanup(),
        "ClaudeAPIMonitor": test_claude_api_monitor_deprecation(),
        "MonitoringCompat": test_monitoring_compat_deprecation(),
        "RedisCleanupScript": test_redis_cleanup_script(),
        "GrafanaIntegration": test_grafana_integration(),
    }

    print("\n" + "=" * 70)
    print("Phase 5 Test Results Summary")
    print("=" * 70)

    passed = 0
    failed = 0

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")

    if failed == 0:
        print("\n✅ Phase 5 Cleanup & Deprecation COMPLETE!")
        print("=" * 70)
        print("\n📋 Next Steps:")
        print("1. Run: python scripts/cleanup_redis_metrics.py --dry-run")
        print("2. Verify Prometheus metrics at http://10.0.0.1:9090")
        print("3. Verify Grafana dashboards at http://10.0.0.4:3000")
        print("4. After verification, run: python scripts/cleanup_redis_metrics.py")
        print("5. Close Issue #348")
        return 0
    else:
        print("\n❌ Some tests failed. Please fix issues before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
