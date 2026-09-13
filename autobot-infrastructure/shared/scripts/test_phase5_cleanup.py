#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# NOTE: Test/CLI tool uses print() for user-facing output per LOGGING_STANDARDS.md
"""
Test script for Phase 5 Cleanup & Deprecation (Issue #348)

Validates that:
1. Legacy in-memory buffers have been removed from metrics collectors
2. Redis persistence has been removed
3. Prometheus is the primary metrics store
4. Deprecated modules are gone and their successors are defined
5. Grafana integration is functional

Monitoring compatibility layer (#14870): ``backend/api/monitoring_compat.py`` was
DELETED by #3354 ("delete dead code mesh_brain.py and monitoring_compat.py"), so
importing it -- as this script used to -- raised ModuleNotFoundError and killed the
whole run before a single result printed. Its deletion IS the Phase 5 cleanup having
landed, so the check now asserts (a) the module is absent and (b) each surviving
handler is defined in the module it was re-homed into, resolved by AST-parsing the
file text rather than importing the backend app. The deprecation mechanism
(``DEPRECATION_MSG`` + ``warnings.warn``) was deliberately not carried over, so it is
no longer looked for. ``get_workflow_summary`` has no successor at all and is
reported as a SKIPPED gap rather than silently dropped.

ClaudeAPIMonitor (#16282): the SLM's ``monitoring/claude_api_monitor.py``, which
Phase 5 marked DEPRECATED, was retired. Its callers record through the Prometheus
metrics manager, so the check asserts the file is absent and that the manager still
defines ``record_claude_api_request`` -- read from the file tree, like the compat
check, rather than imported.
"""

import ast
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import NamedTuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# #14518: the checks below import ``utils.*`` from autobot-backend, which was not
# on sys.path, so the script raised ModuleNotFoundError on its own import block.
# Add it the way the other operator entry points in this tree do (#14129). The
# SLM tree was added here too while the ClaudeAPIMonitor check imported
# ``monitoring.claude_api_monitor``; that module is retired (#16282) and the check
# reads files instead, so nothing here imports from the SLM.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = str(_REPO_ROOT / "autobot-backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

PASSED = "PASSED"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
_ICONS = {PASSED: "✅", FAILED: "❌", SKIPPED: "⏭️"}


class CheckResult(NamedTuple):
    """Outcome of one check: a PASSED/FAILED/SKIPPED state plus a one-line reason."""

    state: str
    reason: str = ""


# Attributes Phase 5 removed from the metrics collectors.
REMOVED_SYSTEM_ATTRS = (
    "_metrics_buffer",
    "_retention_hours",
    "_get_redis_client",
    "store_metrics",
    "get_recent_metrics",
)
REMOVED_ERROR_ATTRS = ("_persist_metric", "get_recent_errors")

# The compat module #3354 deleted; its absence is what Phase 5 was meant to achieve.
COMPAT_MODULE = "autobot-backend/api/monitoring_compat.py"

# The SLM module Phase 5 deprecated and #16282 retired, and the recorder its callers use now.
CLAUDE_API_MONITOR_MODULE = "autobot-slm-backend/monitoring/claude_api_monitor.py"
CLAUDE_API_RECORDER = ("autobot_shared/monitoring/prometheus_metrics.py", "record_claude_api_request")

# Old compat handler name -> (module it was re-homed into, name it is defined under).
REHOMED_HANDLERS = {
    "get_system_metrics_current": ("autobot-backend/api/metrics.py", "get_current_system_metrics"),
    "get_system_metrics_history": ("autobot-backend/api/metrics.py", "get_system_metrics_history"),
    "get_recent_errors": ("autobot-backend/api/error_monitoring.py", "get_recent_errors"),
    "get_claude_api_status": ("autobot-backend/api/monitoring.py", "get_claude_api_status"),
    "get_services_health": ("autobot-backend/api/monitoring.py", "get_services_health"),
    "get_github_status": ("autobot-backend/api/monitoring.py", "get_github_status"),
}

# Compat handlers that were dropped outright and never re-homed.
UNRESOLVED_HANDLERS = {
    "get_workflow_summary": "no successor route or function anywhere after #3354 dissolved the compat layer",
}

GRAFANA_DASHBOARDS = (
    "autobot-overview.json",
    "autobot-system.json",
    "autobot-workflow.json",
    "autobot-errors.json",
    "autobot-claude-api.json",
    "autobot-github.json",
)
# #14870: the component never lived under autobot-vue/src/components/monitoring/.
GRAFANA_VUE_COMPONENT = "autobot-slm-frontend/src/components/monitoring/GrafanaDashboard.vue"

print("=" * 70)
print("Testing Phase 5 Cleanup & Deprecation (Issue #348)")
print("=" * 70)


def _check_removed_attrs(obj, attrs):
    """Print one line per attribute; return the first one that still exists."""
    for attr in attrs:
        if hasattr(obj, attr):
            print(f"  ❌ {attr} still exists (should be removed)")
            return attr
        print(f"  ✅ {attr} removed")
    return None


def _report_prometheus(obj):
    """Print whether the collector carries its Prometheus integration."""
    if hasattr(obj, "prometheus"):
        print("  ✅ Prometheus integration present")
    else:
        print("  ⚠️  Prometheus integration not found (expected)")


def _defines_function(source_path: Path, func_name: str) -> bool:
    """AST-parse ``source_path`` and report whether it defines ``func_name``."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name for node in ast.walk(tree)
    )


def test_system_metrics_cleanup() -> CheckResult:
    """Test that SystemMetricsCollector has been cleaned up."""
    print("\n✓ SystemMetricsCollector Cleanup:")

    from utils.system_metrics import SystemMetricsCollector

    collector = SystemMetricsCollector()
    survivor = _check_removed_attrs(collector, REMOVED_SYSTEM_ATTRS)
    if survivor:
        return CheckResult(FAILED, f"SystemMetricsCollector.{survivor} still exists")

    _report_prometheus(collector)
    return CheckResult(PASSED)


def test_error_metrics_cleanup() -> CheckResult:
    """Test that ErrorMetricsCollector has been cleaned up."""
    print("\n✓ ErrorMetricsCollector Cleanup:")

    from utils.error_metrics import ErrorMetricsCollector

    collector = ErrorMetricsCollector()
    survivor = _check_removed_attrs(collector, REMOVED_ERROR_ATTRS)
    if survivor:
        return CheckResult(FAILED, f"ErrorMetricsCollector.{survivor} still exists")

    _report_prometheus(collector)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = ErrorMetricsCollector(redis_client="fake_client")
        if any("deprecated" in str(warning.message).lower() for warning in caught):
            print("  ✅ redis_client deprecation warning emitted")
        else:
            print("  ⚠️  redis_client deprecation warning not captured (may use logger)")

    return CheckResult(PASSED)


def test_claude_api_monitor_removed() -> CheckResult:
    """Assert the deprecated ClaudeAPIMonitor is gone (#16282) and its Prometheus successor is defined."""
    print("\n✓ ClaudeAPIMonitor (retired by #16282):")

    if (_REPO_ROOT / CLAUDE_API_MONITOR_MODULE).exists():
        print(f"  ❌ {CLAUDE_API_MONITOR_MODULE} still exists")
        return CheckResult(FAILED, f"{CLAUDE_API_MONITOR_MODULE} still exists")
    print(f"  ✅ {CLAUDE_API_MONITOR_MODULE} removed")

    rel_path, name = CLAUDE_API_RECORDER
    target = _REPO_ROOT / rel_path
    if not (target.is_file() and _defines_function(target, name)):
        print(f"  ❌ {name} not defined in {rel_path}")
        return CheckResult(FAILED, f"successor {rel_path}::{name} missing")
    print(f"  ✅ successor {rel_path}::{name}")
    return CheckResult(PASSED)


def test_monitoring_compat_deprecation() -> CheckResult:
    """Assert the compat layer is gone (#3354) and its handlers live in their new homes."""
    print("\n✓ Monitoring Compatibility Layer (deleted by #3354):")

    if (_REPO_ROOT / COMPAT_MODULE).exists():
        print(f"  ❌ {COMPAT_MODULE} still exists - Phase 5 cleanup has not landed")
        return CheckResult(FAILED, f"{COMPAT_MODULE} still exists")
    print(f"  ✅ {COMPAT_MODULE} removed")

    unresolved = []
    for old_name, (rel_path, new_name) in REHOMED_HANDLERS.items():
        target = _REPO_ROOT / rel_path
        if target.is_file() and _defines_function(target, new_name):
            print(f"  ✅ {old_name} -> {rel_path}::{new_name}")
        else:
            print(f"  ❌ {old_name} -> {new_name} not defined in {rel_path}")
            unresolved.append(f"{old_name} -> {rel_path}::{new_name}")

    for old_name, reason in UNRESOLVED_HANDLERS.items():
        print(f"  ⏭️  {old_name} SKIPPED - {reason}")

    if unresolved:
        return CheckResult(FAILED, "re-homed handler(s) missing: " + ", ".join(unresolved))
    gaps = "; ".join(f"{name} ({reason})" for name, reason in UNRESOLVED_HANDLERS.items())
    return CheckResult(SKIPPED, f"known gap: {gaps}")


def test_redis_cleanup_script() -> CheckResult:
    """Test that Redis cleanup script exists and is valid."""
    print("\n✓ Redis Cleanup Script:")

    script_path = Path(__file__).parent / "cleanup_redis_metrics.py"
    if not script_path.exists():
        print("  ❌ cleanup_redis_metrics.py not found")
        return CheckResult(FAILED, "cleanup_redis_metrics.py not found")
    print("  ✅ cleanup_redis_metrics.py exists")

    content = script_path.read_text(encoding="utf-8")
    for token in ("LEGACY_KEY_PATTERNS", "--dry-run"):
        if token not in content:
            print(f"  ❌ {token} not found")
            return CheckResult(FAILED, f"{token} missing from cleanup_redis_metrics.py")
        print(f"  ✅ {token} present")

    for pattern in ("metrics:system:", "error_metrics:", "kb_cache_stats"):
        marker = "✅" if pattern in content else "⚠️ "
        print(f"  {marker} Pattern '{pattern}'")

    return CheckResult(PASSED)


def test_grafana_integration() -> CheckResult:
    """Test that Grafana dashboards and the embedding Vue component are in place."""
    print("\n✓ Grafana Integration:")

    dashboard_dir = Path(__file__).parent.parent / "config" / "grafana" / "dashboards"
    missing = []
    for dashboard in GRAFANA_DASHBOARDS:
        if (dashboard_dir / dashboard).exists():
            print(f"  ✅ {dashboard}")
        else:
            print(f"  ❌ {dashboard} not found")
            missing.append(dashboard)

    if (_REPO_ROOT / GRAFANA_VUE_COMPONENT).is_file():
        print(f"  ✅ {GRAFANA_VUE_COMPONENT}")
    else:
        print(f"  ❌ {GRAFANA_VUE_COMPONENT} not found")
        missing.append(GRAFANA_VUE_COMPONENT)

    if missing:
        return CheckResult(FAILED, "missing: " + ", ".join(missing))
    return CheckResult(PASSED)


# Each entry declares the exceptions its check can legitimately raise, so one
# broken check is recorded as FAILED instead of killing the whole run (#14870).
CHECKS = (
    ("SystemMetricsCollector", test_system_metrics_cleanup, (ImportError, AttributeError, TypeError)),
    ("ErrorMetricsCollector", test_error_metrics_cleanup, (ImportError, AttributeError, TypeError)),
    ("ClaudeAPIMonitor", test_claude_api_monitor_removed, (OSError, SyntaxError, UnicodeDecodeError)),
    ("MonitoringCompat", test_monitoring_compat_deprecation, (OSError, SyntaxError, UnicodeDecodeError)),
    ("RedisCleanupScript", test_redis_cleanup_script, (OSError, UnicodeDecodeError)),
    ("GrafanaIntegration", test_grafana_integration, (OSError,)),
)


def _run_check(name, check, expected_exceptions) -> CheckResult:
    """Run one check; turn its declared failure modes into a FAILED result."""
    try:
        return check()
    except expected_exceptions as exc:
        print(f"\n  ❌ {name} raised {type(exc).__name__}: {exc}")
        return CheckResult(FAILED, f"{type(exc).__name__}: {exc}")


def _print_next_steps():
    """Print the Phase 5 follow-up checklist once every check has passed."""
    print("\n✅ Phase 5 Cleanup & Deprecation COMPLETE!")
    print("=" * 70)
    print("\n📋 Next Steps:")
    print("1. Run: python scripts/cleanup_redis_metrics.py --dry-run")
    print("2. Verify Prometheus metrics on the monitoring host")
    print("3. Verify Grafana dashboards on the monitoring host")
    print("4. After verification, run: python scripts/cleanup_redis_metrics.py")
    print("5. Close Issue #348")


def main():
    """Run every Phase 5 check and summarise PASSED/FAILED/SKIPPED counts."""
    results = {name: _run_check(name, check, excs) for name, check, excs in CHECKS}

    print("\n" + "=" * 70)
    print("Phase 5 Test Results Summary")
    print("=" * 70)
    for name, outcome in results.items():
        detail = f" - {outcome.reason}" if outcome.reason else ""
        print(f"  {name}: {_ICONS[outcome.state]} {outcome.state}{detail}")

    counts = Counter(outcome.state for outcome in results.values())
    print(f"\nTotal: {counts[PASSED]} passed, {counts[FAILED]} failed, {counts[SKIPPED]} skipped")
    for name, outcome in results.items():
        if outcome.state == SKIPPED:
            print(f"  ⏭️  SKIPPED {name}: {outcome.reason}")

    if counts[FAILED]:
        print("\n❌ Some checks failed. Please fix them before proceeding.")
        return 1
    if counts[SKIPPED]:
        print("\n⚠️  No failures, but known gaps remain - Issue #348 cannot be closed yet.")
        return 0
    _print_next_steps()
    return 0


if __name__ == "__main__":
    sys.exit(main())
