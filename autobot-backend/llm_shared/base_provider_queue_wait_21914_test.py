# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider latency excludes the concurrency/rate-limit queue wait (#21914).

``chat_completion`` used to start its latency clock before waiting on the
per-provider semaphore, so a queued call reported provider time plus queue
time. The clock now starts once the slot and rate-limit token are held and the
wait is recorded separately as ``response.metadata["queue_wait_ms"]``.

A fake monotonic clock stands in for wall time so the test is deterministic.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import AsyncIterator, List

import pytest

from . import base_provider, rate_limit_backoff
from .base_provider import BaseProvider
from .models import LLMRequest, LLMResponse
from .rate_limit_backoff import RateLimitError

HOLD_S = 5.0
PROVIDER_S = 0.25


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


class _TimedProvider(BaseProvider):
    """Provider whose call takes ``PROVIDER_S`` of fake time."""

    def __init__(self, clock: _FakeClock) -> None:
        super().__init__({"max_concurrent_requests": 1})
        self.provider_name = "qwtest-21914"
        self._clock = clock

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        self._clock.now += PROVIDER_S
        return LLMResponse(content="ok", provider=self.provider_name)

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        yield ""

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> List[str]:
        return []


class _PassthroughBreaker:
    is_rejecting = False

    async def call_async(self, fn):
        return await fn()


class _NoRetry:
    async def execute_with_retry(self, fn, provider=None):
        return await fn()


class _OpenGate:
    async def evaluate(self, request):
        return None

    async def record(self, request, response):
        return None


@pytest.fixture
def observed(monkeypatch):
    """Patch every collaborator of chat_completion; return the recorded observations."""
    clock = _FakeClock()
    seen: list = []
    errors: list = []

    @asynccontextmanager
    async def _token(_key):
        yield

    monkeypatch.setattr(base_provider, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(base_provider, "get_llm_rate_limiter", lambda: SimpleNamespace(acquire=_token))
    monkeypatch.setattr(base_provider, "get_backoff_handler", lambda: _NoRetry())
    monkeypatch.setattr(base_provider, "get_token_budget_gate", lambda: _OpenGate())
    monkeypatch.setattr(BaseProvider, "_completion_circuit_breaker", lambda self: _PassthroughBreaker())
    monkeypatch.setattr(BaseProvider, "_notify_request_started", staticmethod(lambda r, k: None))
    monkeypatch.setattr(BaseProvider, "_notify_error", staticmethod(lambda e, r: errors.append(e)))
    monkeypatch.setattr(BaseProvider, "_notify_response", staticmethod(lambda resp, ms: seen.append((resp, ms))))
    return clock, seen, errors


async def test_latency_excludes_semaphore_wait_and_queue_wait_includes_it(observed):
    clock, seen, _errors = observed
    provider = _TimedProvider(clock)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

    await provider._concurrency_semaphore.acquire()  # another call holds the only slot
    call = asyncio.create_task(provider.chat_completion(request))
    await asyncio.sleep(0)  # let the call reach the semaphore and queue
    assert not call.done()

    clock.now += HOLD_S  # the other call holds the slot for a known delay
    provider._concurrency_semaphore.release()
    response = await call

    assert len(seen) == 1
    _, latency_ms = seen[0]
    assert latency_ms == pytest.approx(PROVIDER_S * 1000)
    assert response.metadata["queue_wait_ms"] == pytest.approx(HOLD_S * 1000)


async def test_uncontended_call_records_zero_queue_wait(observed):
    clock, seen, _errors = observed
    provider = _TimedProvider(clock)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

    response = await provider.chat_completion(request)

    assert seen[0][1] == pytest.approx(PROVIDER_S * 1000)
    assert response.metadata["queue_wait_ms"] == 0.0


async def test_failure_in_guarded_completion_notifies_error_once(observed, monkeypatch):
    clock, seen, errors = observed
    provider = _TimedProvider(clock)
    boom = RuntimeError("boom")

    async def _raise(_request):
        raise boom

    monkeypatch.setattr(provider, "_guarded_completion", _raise)

    with pytest.raises(RuntimeError, match="boom"):
        await provider.chat_completion(LLMRequest(messages=[{"role": "user", "content": "hi"}]))

    assert errors == [boom]
    assert seen == []


async def test_cancellation_while_queued_notifies_error_once(observed):
    clock, seen, errors = observed
    provider = _TimedProvider(clock)

    await provider._concurrency_semaphore.acquire()  # the only slot is held
    call = asyncio.create_task(provider.chat_completion(LLMRequest(messages=[{"role": "user", "content": "hi"}])))
    await asyncio.sleep(0)  # the call is now queued on the semaphore
    call.cancel()

    with pytest.raises(asyncio.CancelledError):
        await call

    assert len(errors) == 1
    assert isinstance(errors[0], asyncio.CancelledError)
    assert seen == []
    provider._concurrency_semaphore.release()


class _RateLimitedOnceProvider(_TimedProvider):
    """Answers a provider rate limit once, then succeeds (#21929)."""

    def __init__(self, clock: _FakeClock) -> None:
        super().__init__(clock)
        self.calls = 0

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(content="", provider=self.provider_name, error="429 Too Many Requests")
        return await super()._chat_completion_impl(request)


class _RetryOnRateLimit:
    """The backoff handler's contract: a RateLimitError is retried as a NEW attempt."""

    async def execute_with_retry(self, fn, provider=None):
        try:
            return await fn()
        except RateLimitError:
            return await fn()


async def test_a_rate_limited_attempt_ends_in_one_error_and_the_retry_in_one_completion(observed, monkeypatch):
    clock, seen, errors = observed
    started: list = []
    monkeypatch.setattr(base_provider, "get_backoff_handler", lambda: _RetryOnRateLimit())
    monkeypatch.setattr(BaseProvider, "_notify_request_started", staticmethod(lambda r, k: started.append(k)))
    monkeypatch.setattr(rate_limit_backoff, "_persist_headroom_from_429", lambda *a: None)
    provider = _RateLimitedOnceProvider(clock)

    response = await provider.chat_completion(LLMRequest(messages=[{"role": "user", "content": "hi"}]))

    assert response.content == "ok"
    assert len(errors) == 1 and isinstance(errors[0], RateLimitError)  # the 429 stays visible as an error
    assert len(seen) == 1 and seen[0][0] is response  # only the successful attempt completes
    assert len(started) == len(errors) + len(seen) == 2  # one terminal event per started attempt
