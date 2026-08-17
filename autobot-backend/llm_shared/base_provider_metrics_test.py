# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reproduction test for #14211: LLMProviderMetricsRecorder had zero callers.

Starts from ``BaseProvider.chat_completion`` — the seam every real LLM
provider request goes through — rather than calling ``PrometheusObserver``
or the recorder directly, per the issue's verification bar ("start the test
where a provider request originates").
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, List

import pytest

from .base_provider import BaseProvider
from .models import LLMRequest, LLMResponse
from .observability import registry as obs_registry
from .observability.prometheus_observer import PrometheusObserver
from .types import LLMType


class _SpyMetricsManager:
    """Records every call PrometheusObserver makes to the LLM provider recorder."""

    def __init__(self) -> None:
        self.request_starts: list[str] = []
        self.request_completes: list[tuple] = []
        self.tokens: list[tuple] = []
        self.costs: list[tuple] = []
        self.errors: list[tuple] = []

    def record_llm_request_start(self, provider: str) -> None:
        self.request_starts.append(provider)

    def record_llm_request_complete(
        self,
        provider: str,
        model: str,
        request_type: str,
        latency_seconds: float,
        time_to_first_token_seconds: float = 0,
    ) -> None:
        self.request_completes.append((provider, model, request_type, latency_seconds, time_to_first_token_seconds))

    def record_llm_tokens(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self.tokens.append((provider, model, input_tokens, output_tokens))

    def record_llm_cost(self, provider: str, model: str, input_cost: float, output_cost: float) -> None:
        self.costs.append((provider, model, input_cost, output_cost))

    def record_llm_error(self, provider: str, model: str, error_type: str) -> None:
        self.errors.append((provider, model, error_type))

    def record_inference_session_complete(self, model: str, duration_seconds: float) -> None:
        pass


class _FakeCostTracker:
    """Deterministic stand-in for services.llm_cost_tracker.LLMCostTracker."""

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return round((input_tokens + output_tokens) * 0.000001, 6)


class _ScriptedProvider(BaseProvider):
    """Provider whose _chat_completion_impl replays one scripted response.

    Mirrors ``base_provider_breaker_test.py``'s ``_ScriptedProvider`` — the
    established pattern in this package for exercising ``chat_completion``
    end-to-end.
    """

    def __init__(self, name: str, response: LLMResponse) -> None:
        super().__init__({})
        self.provider_name = name
        self._response = response

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        return self._response

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        yield ""

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> List[str]:
        return []


@pytest.fixture()
def spy_metrics(monkeypatch):
    """Replace the real Prometheus metrics manager and cost tracker singletons
    with deterministic spies, via the same lazy-import seam PrometheusObserver
    uses in production."""
    spy = _SpyMetricsManager()
    monkeypatch.setattr(
        "autobot_shared.monitoring.prometheus_metrics.get_metrics_manager",
        lambda: spy,
    )
    monkeypatch.setattr(
        "services.llm_cost_tracker.get_cost_tracker",
        lambda: _FakeCostTracker(),
    )
    return spy


@pytest.fixture(autouse=True)
def _isolated_observer_registry():
    """Only PrometheusObserver registered — avoids other observers (OTel,
    LangFuse/LangSmith if enabled via env) adding noise to these assertions."""
    obs_registry.clear()
    obs_registry.register(PrometheusObserver())
    yield
    obs_registry.clear()


async def _run_and_flush(coro):
    """Await *coro*, then wait for every asyncio task it spawned via
    ``create_task`` — base_provider.py's notify_request/_response/_error calls
    are deliberately fire-and-forget, so their side effects are not guaranteed
    to have landed the instant ``coro`` returns."""
    before = set(asyncio.all_tasks())
    result = await coro
    spawned = set(asyncio.all_tasks()) - before - {asyncio.current_task()}
    if spawned:
        await asyncio.wait_for(asyncio.gather(*spawned, return_exceptions=True), timeout=5.0)
    return result


def _request() -> LLMRequest:
    return LLMRequest(messages=[{"role": "user", "content": "hi"}], llm_type=LLMType.CHAT)


class TestMetricsReachRecorderFromProviderRequest:
    """#14211: a real LLM provider request must reach LLMProviderMetricsRecorder.

    This is the AC6 evidence list (autobot_llm_requests_total,
    autobot_llm_tokens_total, autobot_llm_time_to_first_token_seconds_bucket)
    reproduced at the unit level: BaseProvider.chat_completion is called
    exactly as a real provider would be dispatched, never the recorder or
    the observer directly.
    """

    async def test_successful_request_reaches_recorder(self, spy_metrics):
        response = LLMResponse(
            content="hello",
            model="test-model",
            provider="cbtest-metrics",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            time_to_first_token_seconds=0.25,
        )
        provider = _ScriptedProvider("cbtest-metrics", response)

        result = await _run_and_flush(provider.chat_completion(_request()))

        assert result.content == "hello"
        assert spy_metrics.request_starts == ["cbtest-metrics"]

        assert len(spy_metrics.request_completes) == 1
        provider_name, model, request_type, latency_seconds, ttft = spy_metrics.request_completes[0]
        assert provider_name == "cbtest-metrics"
        assert model == "test-model"
        assert request_type == "chat"
        assert latency_seconds > 0.0
        assert ttft == 0.25

        assert spy_metrics.tokens == [("cbtest-metrics", "test-model", 10, 5)]
        assert len(spy_metrics.costs) == 1
        assert spy_metrics.costs[0][0] == "cbtest-metrics"
        assert spy_metrics.costs[0][2] > 0.0  # input_cost, from _FakeCostTracker
        assert not spy_metrics.errors

    async def test_request_without_usage_skips_token_and_cost_but_still_completes(self, spy_metrics):
        response = LLMResponse(content="hello", model="test-model", provider="cbtest-metrics-2")
        provider = _ScriptedProvider("cbtest-metrics-2", response)

        await _run_and_flush(provider.chat_completion(_request()))

        assert spy_metrics.request_starts == ["cbtest-metrics-2"]
        assert len(spy_metrics.request_completes) == 1
        assert not spy_metrics.tokens
        assert not spy_metrics.costs


class TestRequestTypeLabel:
    """BaseProvider._request_type_label must yield a plain string (#14211).

    ``LLMType`` subclasses ``str`` for equality/dict-lookup interop, but
    ``Enum.__str__`` still wins over the ``str`` mixin: ``str(LLMType.GENERAL)
    == "LLMType.GENERAL"``, not ``"general"``. A Prometheus label wants the
    latter.
    """

    def test_enum_member_yields_bare_value(self):
        request = LLMRequest(messages=[], llm_type=LLMType.GENERAL)
        assert BaseProvider._request_type_label(request) == "general"

    def test_raw_string_passes_through(self):
        request = LLMRequest(messages=[], llm_type="rag")
        assert BaseProvider._request_type_label(request) == "rag"


class TestErrorReachesRecorder:
    """PrometheusObserver.on_error forwards to record_llm_error (#14211).

    Driving a genuine raised exception through the full backoff/retry
    pipeline (rate-limit retries sleep for real seconds — GH#8502) is slow
    and orthogonal to the AC6 evidence list, so this exercises on_error
    directly with the exact request shape base_provider.py now produces
    (``request.metadata["selected_provider"]`` populated at the top of
    ``chat_completion``, verified separately below).
    """

    async def test_on_error_uses_selected_provider_metadata(self, spy_metrics):
        request = _request()
        request.metadata["selected_provider"] = "cbtest-metrics-error"
        request.model_name = "test-model"
        observer = PrometheusObserver()

        await observer.on_error(ConnectionError("boom"), request)

        assert spy_metrics.errors == [("cbtest-metrics-error", "test-model", "ConnectionError")]

    async def test_on_error_falls_back_to_unknown_without_metadata(self, spy_metrics):
        request = _request()
        observer = PrometheusObserver()

        await observer.on_error(ConnectionError("boom"), request)

        assert spy_metrics.errors == [("unknown", "unknown", "ConnectionError")]


class TestChatCompletionSetsSelectedProvider:
    """chat_completion must populate request.metadata['selected_provider']
    unconditionally (#14211) — the only carrier on_error(exc, request) has for
    which provider actually ran, since notify_error's signature has no
    metadata parameter."""

    async def test_selected_provider_set_even_when_registry_never_ran(self, spy_metrics):
        response = LLMResponse(content="hello", model="test-model", provider="cbtest-metrics-3")
        provider = _ScriptedProvider("cbtest-metrics-3", response)
        request = _request()
        assert "selected_provider" not in request.metadata

        await _run_and_flush(provider.chat_completion(request))

        assert request.metadata["selected_provider"] == "cbtest-metrics-3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
