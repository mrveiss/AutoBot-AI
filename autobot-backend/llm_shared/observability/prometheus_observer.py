# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
PrometheusObserver — record LLM inference metrics via the shared metrics manager (GH#6593).

Extracted from ``llm_shared.optimization.profiler.export_to_prometheus`` so
that Prometheus export is pluggable and no longer tied to the Profiler lifecycle.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class PrometheusObserver:
    """Record per-call LLM latency and token counters in Prometheus."""

    async def on_request(self, request, metadata: dict) -> None:
        pass

    async def on_response(self, response, latency_ms: float, cost: float) -> None:
        try:
            self._record(response, latency_ms)
        except Exception:
            logger.debug("Prometheus export skipped — metrics not available")

    async def on_error(self, exc: Exception, request) -> None:
        pass

    def _record(self, response, latency_ms: float) -> None:
        from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

        metrics = get_metrics_manager()
        model = response.model or response.provider or "unknown"
        total_s = latency_ms / 1000.0
        metrics.record_inference_session_complete(model, total_s)
        usage = response.usage or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        if prompt_tokens or completion_tokens:
            metrics.record_inference_stage_duration(model, "prompt", prompt_tokens / 1000.0)
            metrics.record_inference_stage_duration(model, "completion", completion_tokens / 1000.0)
