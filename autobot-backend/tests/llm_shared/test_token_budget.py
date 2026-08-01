# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the pre-request cumulative token budget gate (Issue #11541).

Covers:
- Disabled by default (TOKEN_BUDGET_PER_RUN <= 0) -> gate is a no-op
- Under budget -> request proceeds (no provider call blocked)
- At/over budget -> gated with an error LLMResponse, never raises
- Cumulative counting across calls (per scope key)
- Redis unavailable -> fails open (allow-all), never hard-blocks
- BaseProvider._guarded_completion integration: budget block short-circuits
  before the breaker is touched (breaker contract untouched)
"""

from typing import AsyncIterator, Dict, List
from unittest.mock import AsyncMock

import pytest

from llm_shared import token_budget
from llm_shared.base_provider import BaseProvider
from llm_shared.models import LLMRequest, LLMResponse


class _FakeRedis:
    """In-memory stand-in for the async Redis client (get/incrby/expire only)."""

    def __init__(self) -> None:
        self._store: Dict[str, int] = {}

    async def get(self, key: str):
        value = self._store.get(key)
        return str(value).encode() if value is not None else None

    async def incrby(self, key: str, amount: int) -> int:
        self._store[key] = self._store.get(key, 0) + amount
        return self._store[key]

    async def expire(self, key: str, ttl: int) -> None:
        return None


class _EchoProvider(BaseProvider):
    """Minimal concrete BaseProvider that always succeeds with a fixed response."""

    provider_name = "echo"

    def __init__(self, tokens_used: int | None = 10) -> None:
        super().__init__(settings={})
        self._tokens_used = tokens_used

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="ok", model="echo-model", tokens_used=self._tokens_used)

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        yield "ok"

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> List[str]:
        return ["echo-model"]


def _request(session_id: str = "run-1", max_tokens: int | None = None) -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": "hello world"}],
        max_tokens=max_tokens,
        metadata={"session_id": session_id},
    )


@pytest.fixture(autouse=True)
def _reset_budget(monkeypatch):
    """Isolate each test: fresh fake Redis + explicit budget (no env leakage)."""
    fake_redis = _FakeRedis()
    monkeypatch.setattr(token_budget.TokenBudgetGate, "_get_redis", AsyncMock(return_value=fake_redis))
    yield fake_redis


class TestTokenBudgetGateDisabledByDefault:
    def test_disabled_by_default(self):
        """#11541 acceptance: ceiling disabled by default."""
        assert token_budget.TOKEN_BUDGET_PER_RUN <= 0

    @pytest.mark.asyncio
    async def test_disabled_gate_is_noop(self, monkeypatch):
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 0)
        gate = token_budget.TokenBudgetGate()
        result = await gate.evaluate(_request())
        assert result is None


class TestTokenBudgetGateEnforcement:
    @pytest.mark.asyncio
    async def test_under_budget_proceeds(self, monkeypatch):
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 1000)
        gate = token_budget.TokenBudgetGate()
        result = await gate.evaluate(_request())
        assert result is None

    @pytest.mark.asyncio
    async def test_over_budget_blocks_with_error_response_no_raise(self, monkeypatch):
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 1)
        gate = token_budget.TokenBudgetGate()
        result = await gate.evaluate(_request(max_tokens=500))
        assert isinstance(result, LLMResponse)
        assert result.error
        assert "budget" in result.error.lower()
        assert result.content == ""

    @pytest.mark.asyncio
    async def test_cumulative_counting_across_calls(self, monkeypatch, _reset_budget):
        """Two calls whose combined usage exceeds the ceiling: 2nd is gated."""
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 11)
        gate = token_budget.TokenBudgetGate()
        req = _request(session_id="cumulative-run")
        response = LLMResponse(content="x", tokens_used=10)

        first = await gate.evaluate(req)
        assert first is None
        await gate.record(req, response)

        second = await gate.evaluate(req)
        assert isinstance(second, LLMResponse)
        assert second.error

    @pytest.mark.asyncio
    async def test_scope_isolation_per_session(self, monkeypatch, _reset_budget):
        """Different session ids ('runs') track independent cumulative counters."""
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 11)
        gate = token_budget.TokenBudgetGate()
        req_a = _request(session_id="run-a")
        req_b = _request(session_id="run-b")

        await gate.record(req_a, LLMResponse(content="x", tokens_used=10))

        assert await gate.evaluate(req_a) is not None  # run-a near/over ceiling
        assert await gate.evaluate(req_b) is None  # run-b untouched

    @pytest.mark.asyncio
    async def test_redis_unavailable_fails_open(self, monkeypatch):
        """A Redis outage must never hard-block LLM calls."""
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 1)
        gate = token_budget.TokenBudgetGate()

        async def _boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(gate, "_get_redis", _boom)
        result = await gate.evaluate(_request(max_tokens=500))
        assert result is None


class TestBaseProviderIntegration:
    """GH#11541: gate lives at BaseProvider._guarded_completion (chat_completion seam)."""

    @pytest.mark.asyncio
    async def test_under_budget_calls_provider(self, monkeypatch):
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 10_000)
        provider = _EchoProvider()
        response = await provider.chat_completion(_request(session_id="under-budget-run"))
        assert response.error is None
        assert response.content == "ok"

    @pytest.mark.asyncio
    async def test_over_budget_short_circuits_before_provider_call(self, monkeypatch):
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 1)
        provider = _EchoProvider()
        provider._chat_completion_impl = AsyncMock(side_effect=AssertionError("provider must not be called"))
        response = await provider.chat_completion(_request(session_id="over-budget-run", max_tokens=500))
        assert response.error is not None
        assert "budget" in response.error.lower()
        provider._chat_completion_impl.assert_not_called()

    @pytest.mark.asyncio
    async def test_breaker_contract_untouched_by_budget_block(self, monkeypatch):
        """A budget block must not register as a circuit-breaker failure."""
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 1)
        provider = _EchoProvider()
        breaker = provider._completion_circuit_breaker()
        failures_before = breaker.failure_count

        await provider.chat_completion(_request(session_id="breaker-check-run", max_tokens=500))

        assert breaker.failure_count == failures_before

    @pytest.mark.asyncio
    async def test_cumulative_usage_recorded_after_success(self, monkeypatch):
        monkeypatch.setattr(token_budget, "TOKEN_BUDGET_PER_RUN", 15)
        provider = _EchoProvider(tokens_used=10)
        session = "record-after-success-run"

        first = await provider.chat_completion(_request(session_id=session))
        assert first.error is None

        # Second call in the same run now exceeds the 15-token ceiling (10 used + new estimate).
        second = await provider.chat_completion(_request(session_id=session, max_tokens=100))
        assert second.error is not None
        assert "budget" in second.error.lower()
