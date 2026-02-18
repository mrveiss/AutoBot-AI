# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Claude API Metrics Recorder

Metrics for Claude API monitoring.
Extracted from PrometheusMetricsManager as part of Issue #394.
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class ClaudeAPIMetricsRecorder(BaseMetricsRecorder):
    """Recorder for Claude API metrics."""

    def _init_metrics(self) -> None:
        """Initialize Claude API metrics."""
        self.claude_api_requests_total = Counter(
            "autobot_claude_api_requests_total",
            "Total Claude API requests",
            ["tool_name", "success"],
            registry=self.registry,
        )

        self.claude_api_payload_bytes = Histogram(
            "autobot_claude_api_payload_bytes",
            "Claude API payload size distribution",
            buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000],
            registry=self.registry,
        )

        self.claude_api_response_time = Histogram(
            "autobot_claude_api_response_time_seconds",
            "Claude API response time in seconds",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

        self.claude_api_rate_limit_remaining = Gauge(
            "autobot_claude_api_rate_limit_remaining",
            "Claude API rate limit remaining",
            registry=self.registry,
        )

    def record_request(self, tool_name: str, success: bool) -> None:
        """Record a Claude API request."""
        self.claude_api_requests_total.labels(
            tool_name=tool_name, success=str(success).lower()
        ).inc()

    def record_payload(self, payload_bytes: int) -> None:
        """Record Claude API payload size."""
        self.claude_api_payload_bytes.observe(payload_bytes)

    def record_response_time(self, response_time_seconds: float) -> None:
        """Record Claude API response time."""
        self.claude_api_response_time.observe(response_time_seconds)

    def update_rate_limit(self, remaining: int) -> None:
        """Update Claude API rate limit remaining."""
        self.claude_api_rate_limit_remaining.set(remaining)


__all__ = ["ClaudeAPIMetricsRecorder"]
