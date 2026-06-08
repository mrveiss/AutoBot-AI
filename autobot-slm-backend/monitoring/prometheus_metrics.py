# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus Metrics for AutoBot SLM backend.

Re-exports the shared implementation from autobot_shared.
Issue #937: Consolidated from local implementation to autobot_shared canonical copy.

The full implementation now lives in:
  autobot_shared/monitoring/prometheus_metrics.py
  autobot_shared/monitoring/metrics/ (domain-specific recorders)
"""

from autobot_shared.monitoring.prometheus_metrics import (  # noqa: F401
    PrometheusMetricsManager,
    get_metrics_manager,
)

__all__ = ["PrometheusMetricsManager", "get_metrics_manager"]
