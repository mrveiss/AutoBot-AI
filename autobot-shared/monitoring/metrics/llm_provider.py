# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Provider Metrics Recorder

Metrics for LLM provider operations including request tracking,
token usage, cost tracking, and error rates.
Created as part of Issue #470 - Add missing Prometheus metrics.

Covers:
- Request counts by provider and model
- Token usage (input/output/total)
- Cost tracking in dollars
- Response latency
- Error rates and types
- Rate limiting
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class LLMProviderMetricsRecorder(BaseMetricsRecorder):
    """Recorder for LLM provider metrics."""

    def _init_metrics(self) -> None:
        """Initialize LLM provider metrics.

        Delegates to helper methods for each metric category.
        Issue #665: Refactored from 149-line monolithic function.
        """
        self._init_request_metrics()
        self._init_token_metrics()
        self._init_cost_metrics()
        self._init_error_metrics()
        self._init_rate_limit_metrics()
        self._init_provider_health_metrics()

    def _init_request_metrics(self) -> None:
        """Initialize request tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.requests_total = Counter(
            "autobot_llm_requests_total",
            "Total LLM requests",
            [
                "provider",
                "model",
                "request_type",
            ],  # request_type: chat, completion, embedding
            registry=self.registry,
        )

        self.requests_in_flight = Gauge(
            "autobot_llm_requests_in_flight",
            "Current number of in-flight requests",
            ["provider"],
            registry=self.registry,
        )

        self.request_latency = Histogram(
            "autobot_llm_request_latency_seconds",
            "LLM request latency in seconds",
            ["provider", "model"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
            registry=self.registry,
        )

        self.time_to_first_token = Histogram(
            "autobot_llm_time_to_first_token_seconds",
            "Time to first token for streaming requests",
            ["provider", "model"],
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.registry,
        )

    def _init_token_metrics(self) -> None:
        """Initialize token tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.tokens_total = Counter(
            "autobot_llm_tokens_total",
            "Total tokens processed",
            ["provider", "model", "token_type"],  # token_type: input, output
            registry=self.registry,
        )

        self.tokens_per_request = Histogram(
            "autobot_llm_tokens_per_request",
            "Tokens per request",
            ["provider", "model", "token_type"],
            buckets=[10, 50, 100, 500, 1000, 2000, 4000, 8000, 16000, 32000],
            registry=self.registry,
        )

        self.context_window_usage = Gauge(
            "autobot_llm_context_window_usage_percent",
            "Context window usage percentage",
            ["provider", "model"],
            registry=self.registry,
        )

    def _init_cost_metrics(self) -> None:
        """Initialize cost tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.cost_dollars = Counter(
            "autobot_llm_cost_dollars_total",
            "Total cost in USD",
            ["provider", "model", "cost_type"],  # cost_type: input, output, total
            registry=self.registry,
        )

        self.cost_per_request = Histogram(
            "autobot_llm_cost_per_request_dollars",
            "Cost per request in USD",
            ["provider", "model"],
            buckets=[0.0001, 0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
            registry=self.registry,
        )

        self.daily_cost_budget_remaining = Gauge(
            "autobot_llm_daily_cost_budget_remaining_dollars",
            "Remaining daily cost budget in USD",
            ["provider"],
            registry=self.registry,
        )

    def _init_error_metrics(self) -> None:
        """Initialize error tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.errors_total = Counter(
            "autobot_llm_errors_total",
            "Total LLM errors",
            [
                "provider",
                "model",
                "error_type",
            ],  # error_type: rate_limit, timeout, auth, api, other
            registry=self.registry,
        )

        self.error_rate = Gauge(
            "autobot_llm_error_rate_percent",
            "Current error rate percentage (rolling window)",
            ["provider"],
            registry=self.registry,
        )

        self.retries_total = Counter(
            "autobot_llm_retries_total",
            "Total retry attempts",
            ["provider", "model", "retry_reason"],
            registry=self.registry,
        )

    def _init_rate_limit_metrics(self) -> None:
        """Initialize rate limiting metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.rate_limit_remaining = Gauge(
            "autobot_llm_rate_limit_remaining",
            "Remaining rate limit quota",
            ["provider", "limit_type"],  # limit_type: requests, tokens
            registry=self.registry,
        )

        self.rate_limit_reset_seconds = Gauge(
            "autobot_llm_rate_limit_reset_seconds",
            "Seconds until rate limit resets",
            ["provider", "limit_type"],
            registry=self.registry,
        )

        self.rate_limited_requests = Counter(
            "autobot_llm_rate_limited_requests_total",
            "Total requests that were rate limited",
            ["provider"],
            registry=self.registry,
        )

    def _init_provider_health_metrics(self) -> None:
        """Initialize provider health metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.provider_available = Gauge(
            "autobot_llm_provider_available",
            "Provider availability (1=available, 0=unavailable)",
            ["provider"],
            registry=self.registry,
        )

        self.provider_latency_p99 = Gauge(
            "autobot_llm_provider_latency_p99_seconds",
            "99th percentile latency (rolling window)",
            ["provider"],
            registry=self.registry,
        )

    # =========================================================================
    # Request Methods
    # =========================================================================

    def record_request_start(self, provider: str) -> None:
        """Record start of an LLM request (increment in-flight)."""
        self.requests_in_flight.labels(provider=provider).inc()

    def record_request_complete(
        self,
        provider: str,
        model: str,
        request_type: str,
        latency_seconds: float,
        time_to_first_token_seconds: float = 0,
    ) -> None:
        """Record completion of an LLM request."""
        self.requests_in_flight.labels(provider=provider).dec()
        self.requests_total.labels(
            provider=provider, model=model, request_type=request_type
        ).inc()
        self.request_latency.labels(provider=provider, model=model).observe(
            latency_seconds
        )
        if time_to_first_token_seconds > 0:
            self.time_to_first_token.labels(provider=provider, model=model).observe(
                time_to_first_token_seconds
            )

    # =========================================================================
    # Token Methods
    # =========================================================================

    def record_tokens(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record token usage for a request."""
        self.tokens_total.labels(  # nosec B106
            provider=provider, model=model, token_type="input"
        ).inc(input_tokens)
        self.tokens_total.labels(  # nosec B106
            provider=provider, model=model, token_type="output"
        ).inc(output_tokens)
        self.tokens_per_request.labels(  # nosec B106
            provider=provider, model=model, token_type="input"
        ).observe(input_tokens)
        self.tokens_per_request.labels(  # nosec B106
            provider=provider, model=model, token_type="output"
        ).observe(output_tokens)

    def set_context_window_usage(
        self, provider: str, model: str, usage_percent: float
    ) -> None:
        """Set context window usage percentage."""
        self.context_window_usage.labels(provider=provider, model=model).set(
            usage_percent
        )

    # =========================================================================
    # Cost Methods
    # =========================================================================

    def record_cost(
        self,
        provider: str,
        model: str,
        input_cost: float,
        output_cost: float,
    ) -> None:
        """Record cost for a request."""
        total_cost = input_cost + output_cost
        self.cost_dollars.labels(provider=provider, model=model, cost_type="input").inc(
            input_cost
        )
        self.cost_dollars.labels(
            provider=provider, model=model, cost_type="output"
        ).inc(output_cost)
        self.cost_dollars.labels(provider=provider, model=model, cost_type="total").inc(
            total_cost
        )
        self.cost_per_request.labels(provider=provider, model=model).observe(total_cost)

    def set_budget_remaining(self, provider: str, remaining_dollars: float) -> None:
        """Set remaining daily budget."""
        self.daily_cost_budget_remaining.labels(provider=provider).set(
            remaining_dollars
        )

    # =========================================================================
    # Error Methods
    # =========================================================================

    def record_error(self, provider: str, model: str, error_type: str) -> None:
        """Record an LLM error."""
        # Decrement in-flight on error
        self.requests_in_flight.labels(provider=provider).dec()
        self.errors_total.labels(
            provider=provider, model=model, error_type=error_type
        ).inc()

    def record_retry(self, provider: str, model: str, retry_reason: str) -> None:
        """Record a retry attempt."""
        self.retries_total.labels(
            provider=provider, model=model, retry_reason=retry_reason
        ).inc()

    def set_error_rate(self, provider: str, error_rate_percent: float) -> None:
        """Set current error rate percentage."""
        self.error_rate.labels(provider=provider).set(error_rate_percent)

    # =========================================================================
    # Rate Limit Methods
    # =========================================================================

    def update_rate_limits(
        self,
        provider: str,
        requests_remaining: int,
        tokens_remaining: int,
        reset_seconds: float,
    ) -> None:
        """Update rate limit metrics from API response headers."""
        self.rate_limit_remaining.labels(provider=provider, limit_type="requests").set(
            requests_remaining
        )
        self.rate_limit_remaining.labels(provider=provider, limit_type="tokens").set(
            tokens_remaining
        )
        self.rate_limit_reset_seconds.labels(
            provider=provider, limit_type="requests"
        ).set(reset_seconds)

    def record_rate_limited(self, provider: str) -> None:
        """Record a rate-limited request."""
        self.rate_limited_requests.labels(provider=provider).inc()

    # =========================================================================
    # Provider Health Methods
    # =========================================================================

    def set_provider_available(self, provider: str, available: bool) -> None:
        """Set provider availability status."""
        self.provider_available.labels(provider=provider).set(1 if available else 0)

    def set_provider_latency_p99(self, provider: str, latency_seconds: float) -> None:
        """Set provider 99th percentile latency."""
        self.provider_latency_p99.labels(provider=provider).set(latency_seconds)


__all__ = ["LLMProviderMetricsRecorder"]
