# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
PrometheusObserver — record LLM inference metrics via the shared metrics manager (GH#6593).

Extracted from ``llm_shared.optimization.profiler.export_to_prometheus`` so
that Prometheus export is pluggable and no longer tied to the Profiler lifecycle.

Issue #14211: ``LLMProviderMetricsRecorder`` (~21 metrics, #470) and the
``AutoBot LLM Providers`` Grafana dashboard (#475) existed with zero emit
calls — every panel rendered ``No Data``. This observer is the seam
``BaseProvider.chat_completion`` already notifies on every real LLM request
(GH#6593); it now forwards those notifications to the LLM provider recorder
in addition to the pre-existing inference-profiler duration metrics.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class PrometheusObserver:
    """Record per-call LLM latency, token, cost and error counters in Prometheus."""

    async def on_request(self, request: Any, metadata: dict) -> None:
        """Record request start — increments the in-flight gauge (#14211)."""
        try:
            self._record_start(metadata)
        except Exception:
            logger.warning("Prometheus llm-request-start export failed", exc_info=True)

    async def on_response(self, response: Any, latency_ms: float, cost: float) -> None:
        try:
            self._record(response, latency_ms)
        except Exception:
            # Issue #14211: this used to swallow every export failure at
            # logger.debug, making a broken exporter invisible.
            logger.warning("Prometheus llm-response export failed", exc_info=True)

    async def on_error(self, exc: Exception, request: Any) -> None:
        """Record a failed LLM request (#14211)."""
        try:
            self._record_error(request, exc)
        except Exception:
            logger.warning("Prometheus llm-error export failed", exc_info=True)

    @staticmethod
    def _record_start(metadata: dict) -> None:
        from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

        provider = (metadata or {}).get("provider") or "unknown"
        get_metrics_manager().record_llm_request_start(provider)

    def _record(self, response: Any, latency_ms: float) -> None:
        from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

        metrics = get_metrics_manager()
        model = response.model or response.provider or "unknown"
        provider = response.provider or "unknown"
        total_s = latency_ms / 1000.0

        # Pre-existing inference-profiler duration metrics (unrelated to #14211).
        metrics.record_inference_session_complete(model, total_s)

        request_type = (response.metadata or {}).get("request_type", "chat")
        ttft = getattr(response, "time_to_first_token_seconds", None) or 0.0
        metrics.record_llm_request_complete(provider, model, request_type, total_s, ttft)

        usage = response.usage or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        if prompt_tokens or completion_tokens:
            # Issue #14211: previously these were fed to
            # record_inference_stage_duration(model, stage, tokens / 1000.0) —
            # a token *count* mislabelled as a stage *duration* in seconds.
            # Token counts now go through the token counters they belong to.
            metrics.record_llm_tokens(provider, model, prompt_tokens, completion_tokens)
            self._record_cost(metrics, provider, model, prompt_tokens, completion_tokens)

        # Note: LLMResponse.error (a non-raising provider error, per the
        # BaseProvider "_chat_completion_impl must not raise" contract) is
        # deliberately not recorded as an autobot_llm_errors_total sample
        # here — on_error (raised exceptions) already covers the paths this
        # observer receives, and some error responses also raise afterwards
        # (raise_if_rate_limited), which would double-count against on_error.
        # Scoped out of #14211; tracked as a follow-up.

    @staticmethod
    def _record_cost(metrics: Any, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Split cost into input/output legs via the canonical cost tracker."""
        from services.llm_cost_tracker import get_cost_tracker

        tracker = get_cost_tracker()
        input_cost = tracker.calculate_cost(model, prompt_tokens, 0)
        output_cost = tracker.calculate_cost(model, 0, completion_tokens)
        metrics.record_llm_cost(provider, model, input_cost, output_cost)

    @staticmethod
    def _record_error(request: Any, exc: Exception) -> None:
        from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

        provider = (getattr(request, "metadata", None) or {}).get("selected_provider") or "unknown"
        model = getattr(request, "model_name", None) or "unknown"
        error_type = type(exc).__name__
        get_metrics_manager().record_llm_error(provider, model, error_type)
