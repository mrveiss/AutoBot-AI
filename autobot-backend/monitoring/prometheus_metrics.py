# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus Metrics for AutoBot user backend.

Re-exports the shared implementation from autobot-shared.
Issue #937: Replaced the no-op stub with the real Prometheus implementation.
"""

from autobot_shared.monitoring.prometheus_metrics import (  # noqa: F401
    PrometheusMetricsManager,
    get_metrics_manager,
)

__all__ = ["PrometheusMetricsManager", "get_metrics_manager"]
