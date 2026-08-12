# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in
``PerformanceMonitor._push_alerts_to_prometheus`` (#14047)."""

from unittest.mock import MagicMock

from constants.threshold_constants import CategoryDefaults
from utils.performance_monitoring.monitor import PerformanceMonitor


def _bare_monitor():
    """A PerformanceMonitor instance without running the heavy __init__."""
    monitor = object.__new__(PerformanceMonitor)
    monitor._prometheus = MagicMock()
    return monitor


def test_missing_category_defaults_to_unknown():
    monitor = _bare_monitor()

    monitor._push_alerts_to_prometheus([{"severity": "warning"}])

    monitor._prometheus.record_performance_alert.assert_called_once_with(
        CategoryDefaults.UNKNOWN, "warning"
    )


def test_explicit_category_overrides_default():
    monitor = _bare_monitor()

    monitor._push_alerts_to_prometheus([{"category": "cpu", "severity": "critical"}])

    monitor._prometheus.record_performance_alert.assert_called_once_with("cpu", "critical")
