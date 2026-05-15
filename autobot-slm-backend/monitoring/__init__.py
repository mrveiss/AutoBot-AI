# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Monitoring Package

This package provides monitoring and metrics collection for AutoBot,
including Prometheus metrics for timeout tracking and performance monitoring.
"""

from monitoring.prometheus_metrics import (
    PrometheusMetricsManager,
    get_metrics_manager,
)

__all__ = ["PrometheusMetricsManager", "get_metrics_manager"]
