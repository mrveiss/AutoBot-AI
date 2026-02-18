# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus Metrics for AutoBot SLM backend.

Re-exports the shared implementation from autobot-shared.
Issue #937: Consolidated from local implementation to autobot-shared canonical copy.

The full implementation now lives in:
  autobot-shared/monitoring/prometheus_metrics.py
  autobot-shared/monitoring/metrics/ (domain-specific recorders)
"""

from autobot_shared.monitoring.prometheus_metrics import (  # noqa: F401
    PrometheusMetricsManager,
    get_metrics_manager,
)

__all__ = ["PrometheusMetricsManager", "get_metrics_manager"]
