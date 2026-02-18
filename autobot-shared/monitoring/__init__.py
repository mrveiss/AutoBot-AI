# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Shared Monitoring Package

Single implementation of Prometheus metrics shared by all AutoBot backends.
Moved to autobot-shared in Issue #937 to replace the no-op stub in autobot-backend.
"""

from autobot_shared.monitoring.prometheus_metrics import (
    PrometheusMetricsManager,
    get_metrics_manager,
)

__all__ = ["PrometheusMetricsManager", "get_metrics_manager"]
