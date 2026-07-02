# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Requests Metrics Recorder — Issue #10778

Tracks HTTP API requests via a Prometheus Counter so the BI dashboard can
include them in the total monthly operation count.

Label cardinality is deliberately kept low:
- ``method``       — HTTP verb (GET/POST/PUT/PATCH/DELETE/…)  ≤ 6 distinct values
- ``endpoint``     — matched route template, not the raw URL path, so
                     /api/nodes/abc123 and /api/nodes/xyz789 collapse to
                     ``/api/nodes/{node_id}``                             ≈ 50–100
- ``status_class`` — 2xx / 4xx / 5xx (hundreds digit bucketed)           ≤ 5

Total worst-case cardinality: 6 × 100 × 5 = 3 000 series — within safe Prometheus
limits for a single-process backend.
"""

from prometheus_client import Counter

from .base import BaseMetricsRecorder


class ApiRequestsMetricsRecorder(BaseMetricsRecorder):
    """Recorder for HTTP API request counts."""

    def _init_metrics(self) -> None:
        """Initialize the API request counter."""
        self.requests_total = Counter(
            "autobot_api_requests_total",
            "Total HTTP API requests received by the SLM backend",
            ["method", "endpoint", "status_class"],
            registry=self.registry,
        )

    def record_request(self, method: str, endpoint: str, status_code: int) -> None:
        """Increment the counter for one completed HTTP request.

        Args:
            method:      HTTP verb (e.g. ``GET``, ``POST``).
            endpoint:    FastAPI route template (e.g. ``/api/nodes/{node_id}``).
            status_code: HTTP response status code (e.g. 200, 404, 500).
        """
        status_class = f"{status_code // 100}xx"
        self.requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_class=status_class,
        ).inc()


__all__ = ["ApiRequestsMetricsRecorder"]
