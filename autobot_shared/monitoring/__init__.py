# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Shared Monitoring Package

Single implementation of Prometheus metrics shared by all AutoBot backends.
Moved to autobot_shared in Issue #937 to replace the no-op stub in autobot-backend.
"""

from autobot_shared.monitoring.prometheus_metrics import (
    PrometheusMetricsManager,
    get_metrics_manager,
)
from autobot_shared.monitoring.prometheus_query import (
    list_metric_names,
    query_instant,
    query_range,
)

__all__ = [
    "PrometheusMetricsManager",
    "get_metrics_manager",
    "query_instant",
    "query_range",
    "list_metric_names",
]
