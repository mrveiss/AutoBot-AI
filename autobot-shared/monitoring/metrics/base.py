# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Metrics Recorder

Base class for domain-specific metrics recorders.
"""

from prometheus_client import CollectorRegistry


class BaseMetricsRecorder:
    """Base class for metrics recorders."""

    def __init__(self, registry: CollectorRegistry):
        """
        Initialize the metrics recorder.

        Args:
            registry: Prometheus CollectorRegistry instance
        """
        self.registry = registry
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Initialize metrics. Override in subclasses."""


__all__ = ["BaseMetricsRecorder"]
