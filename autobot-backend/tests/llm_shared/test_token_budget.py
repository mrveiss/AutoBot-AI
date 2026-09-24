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

from pathlib import Path
from typing import AsyncIterator, Dict, List
from unittest.mock import AsyncMock

import pytest

from llm_shared import token_budget
from llm_shared.base_provider import BaseProvider
from llm_shared.models import LLMRequest, LLMResponse


class _FakePipeline:
    """MULTI/EXEC: buffers commands and applies them together on `execute()`.

    Added because the code moved to a transaction and a double that lacks
    `pipeline` does not fail loudly -- with an `AsyncMock` it silently swallows
    every command and the spend counter simply stays at zero, which reads as a
    broken gate rather than a test double missing a method (review finding on
    #17380).

    Each `execute()` appends its command list to `redis.transactions`, so a test
    can assert the increment and the expiry went in ONE transaction rather than
    merely that both happened.
    """

    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._queued: List[tuple] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    def incrby(self, key: str, amount: int) -> "_FakePipeline":
        self._queued.append(("incrby", key, amount))
        return self

    def expire(self, key: str, ttl: int) -> "_FakePipeline":
        self._queued.append(("expire", key, ttl))
        return self

    async def execute(self) -> None:
        self._redis.transactions.append(list(self._queued))
        for command, key, argument in self._queued:
            if command == "incrby":
                await self._redis.incrby(key, argument)
            else:
                await self._redis.expire(key, argument)
        self._queued.clear()


class _FakeRedis:
    """In-memory stand-in for the async Redis client (get/incrby/expire/pipeline)."""

    def __init__(self) -> None:
        self._store: Dict[str, int] = {}
        #: One entry per `pipeline().execute()`, each the commands it carried.
        self.transactions: List[List[tuple]] = []
        #: Keys that ever received an expiry, so a test can tell a key with a
        #: TTL from one left immortal.
        self.expired: Dict[str, int] = {}

    async def get(self, key: str):
        value = self._store.get(key)
        return str(value).encode() if value is not None else None

    async def incrby(self, key: str, amount: int) -> int:
        self._store[key] = self._store.get(key, 0) + amount
        return self._store[key]

    async def expire(self, key: str, ttl: int) -> None:
        self.expired[key] = ttl
        return None

    def pipeline(self, transaction: bool = False) -> _FakePipeline:
        assert transaction, "the budget gate must use a TRANSACTIONAL pipeline"
        return _FakePipeline(self)


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
    """A fresh fake Redis per test, yielded so a test can inspect it.

    It does NOT patch the budget constants, despite what this docstring used to
    claim ("explicit budget (no env leakage)"). It only replaces `_get_redis`.
    Two tests below relied on that promise and asserted the dev-loop budgets
    were disabled, which fails in a process where either environment variable is
    set (review finding on #17380) -- the docstring was the reason the
    assumption looked safe. Tests needing a disabled or a specific budget patch
    the constant themselves.
    """
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


class TestDevLoopBudgetGate:
    """AutoBot's own dev-loop participation budget (#17091): spend (tokens)
    and rate (actions/hour), both pre-flight, both disabled unless configured.
    """

    @pytest.mark.asyncio
    async def test_disabled_by_default_is_a_noop(self, monkeypatch):
        # Patched rather than asserted from the ambient environment (review
        # finding on #17380): a test process with either dev-loop budget set to
        # a positive value failed these assertions, and the failure said the
        # gate was broken rather than that the environment was set. What the
        # test is for is "disabled => no-op", so disabled is a premise to
        # establish, not a condition to hope for.
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 0)
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 0)
        gate = token_budget.TokenBudgetGate()
        assert await gate.evaluate_dev_loop_action(1_000_000) is None

    @pytest.mark.asyncio
    async def test_under_spend_budget_proceeds(self, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 1000)
        gate = token_budget.TokenBudgetGate()
        assert await gate.evaluate_dev_loop_action(100) is None

    @pytest.mark.asyncio
    async def test_over_spend_budget_refuses_without_raising(self, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 100)
        gate = token_budget.TokenBudgetGate()
        refusal = await gate.evaluate_dev_loop_action(200)
        assert isinstance(refusal, token_budget.DevLoopBudgetRefusal)
        assert "token budget" in refusal.reason

    @pytest.mark.asyncio
    async def test_spend_accumulates_across_recorded_actions(self, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 150)
        gate = token_budget.TokenBudgetGate()

        assert await gate.evaluate_dev_loop_action(100) is None
        await gate.record_dev_loop_action(100)

        refusal = await gate.evaluate_dev_loop_action(100)
        assert isinstance(refusal, token_budget.DevLoopBudgetRefusal)

    @pytest.mark.asyncio
    async def test_under_rate_budget_proceeds(self, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 3)
        gate = token_budget.TokenBudgetGate()
        for _ in range(2):
            assert await gate.evaluate_dev_loop_action(1) is None
            await gate.record_dev_loop_action(1)
        assert await gate.evaluate_dev_loop_action(1) is None

    @pytest.mark.asyncio
    async def test_at_rate_budget_refuses_the_next_action(self, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 2)
        gate = token_budget.TokenBudgetGate()
        for _ in range(2):
            assert await gate.evaluate_dev_loop_action(1) is None
            await gate.record_dev_loop_action(1)

        refusal = await gate.evaluate_dev_loop_action(1)
        assert isinstance(refusal, token_budget.DevLoopBudgetRefusal)
        assert "rate budget" in refusal.reason

    @pytest.mark.asyncio
    async def test_spend_is_checked_before_rate(self, monkeypatch):
        """An action already over its spend budget must not also spend a rate
        slot -- evaluate_dev_loop_action must not call record itself."""
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 10)
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 5)
        gate = token_budget.TokenBudgetGate()

        refusal = await gate.evaluate_dev_loop_action(100)

        assert isinstance(refusal, token_budget.DevLoopBudgetRefusal)
        assert "token budget" in refusal.reason
        status = await gate.remaining_dev_loop_budget()
        assert status.actions_this_hour == 0, "evaluate() alone must never record a rate slot"

    @pytest.mark.asyncio
    async def test_remaining_dev_loop_budget_reports_usage(self, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 100)
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 5)
        gate = token_budget.TokenBudgetGate()

        await gate.record_dev_loop_action(30)

        status = await gate.remaining_dev_loop_budget()
        assert status.spend_used == 30
        assert status.spend_budget == 100
        assert status.actions_this_hour == 1
        assert status.rate_budget == 5

    @pytest.mark.asyncio
    async def test_remaining_dev_loop_budget_reports_none_ceiling_when_unconfigured(self, monkeypatch):
        # Same premise, made explicit -- this one assumed it without even
        # asserting it.
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 0)
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 0)
        gate = token_budget.TokenBudgetGate()
        status = await gate.remaining_dev_loop_budget()
        assert status.spend_budget is None
        assert status.rate_budget is None

    @pytest.mark.asyncio
    async def test_redis_unavailable_fails_open(self, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 1)
        gate = token_budget.TokenBudgetGate()

        async def _boom():
            raise ConnectionError("redis is down")

        monkeypatch.setattr(gate, "_get_redis", _boom)

        assert await gate.evaluate_dev_loop_action(1_000_000) is None
        await gate.record_dev_loop_action(1_000_000)  # must not raise either


class TestATtlNeverReachesRedisAsZero:
    """Both budget TTLs are clamped to >= 1 (#17380 review).

    `_increment` hands these straight to `redis.expire`, and EXPIRE with a zero
    or negative TTL DELETES the key. The spend counter would vanish and the next
    check would read zero spend -- a budget that silently stops being a ceiling,
    which is worse than one set too low, because nothing reports it.

    Distinct from the budget VALUES (`TOKEN_BUDGET_PER_RUN`,
    `DEV_LOOP_TOKEN_BUDGET`, `DEV_LOOP_RATE_PER_HOUR`), where 0 deliberately
    disables the gate. A TTL has no such meaning, so 0 there is only a mistake.

    WHY THIS READS SOURCE INSTEAD OF THE CONSTANTS. The constants are computed
    at import, so testing them needs the module re-imported under a patched
    environment, and both ways of doing that fail here: a throwaway
    `spec_from_file_location` copy dies on `token_budget`'s relative imports
    ("attempted relative import with no known parent package"), and
    `importlib.reload` dies under pytest's `--import-mode=importlib` with "spec
    not found for the module". Both were tried before this was written.

    So the assertion is on the call site, which is what a regression would
    change, plus one behavioural check that `env_int_clamped` really clamps --
    without that second half this pins a spelling and trusts a helper.
    """

    _SOURCE = Path(__file__).resolve().parents[2] / "llm_shared" / "token_budget.py"

    @pytest.mark.parametrize(
        "constant,var",
        [
            ("TOKEN_BUDGET_TTL_SECONDS", "AUTOBOT_LLM_TOKEN_BUDGET_TTL_SECONDS"),
            ("DEV_LOOP_BUDGET_TTL_SECONDS", "AUTOBOT_DEV_LOOP_BUDGET_TTL_SECONDS"),
        ],
    )
    def test_the_ttl_is_read_through_a_clamped_helper(self, constant, var):
        source = self._SOURCE.read_text(encoding="utf-8")
        assignment = next(
            (line for line in source.splitlines() if line.startswith(f"{constant}:")),
            None,
        )

        assert assignment is not None, f"{constant} is no longer assigned at module scope"
        assert "env_int_clamped(" in assignment, (
            f"{constant} is read with a helper that does not clamp: {assignment.strip()!r}. "
            "redis.expire would DELETE the spend key on a zero or negative value."
        )
        assert "min_v=1" in assignment, f"{constant} is clamped without a positive floor: {assignment.strip()!r}"
        assert var in assignment, f"{constant} no longer reads {var}"

    @pytest.mark.parametrize(
        "constant",
        ["TOKEN_BUDGET_PER_RUN", "DEV_LOOP_TOKEN_BUDGET", "DEV_LOOP_RATE_PER_HOUR"],
    )
    def test_the_budget_values_are_not_clamped(self, constant):
        """Negative control, and a real requirement: 0 disables those gates.

        It is also what stops the assertion above being satisfied by clamping
        every env read in the file.
        """
        source = self._SOURCE.read_text(encoding="utf-8")
        assignment = next(line for line in source.splitlines() if line.startswith(f"{constant}:"))

        assert (
            "env_int_clamped(" not in assignment
        ), f"{constant} is clamped, but 0 must keep disabling its gate: {assignment.strip()!r}"

    @pytest.mark.parametrize("raw", ["0", "-1"])
    def test_the_clamped_helper_actually_clamps(self, monkeypatch, raw):
        """The other half: the call site is only as good as the helper."""
        from autobot_shared.env_utils import env_int_clamped

        monkeypatch.setenv("AUTOBOT_TTL_CLAMP_PROBE", raw)

        assert env_int_clamped("AUTOBOT_TTL_CLAMP_PROBE", 86400, min_v=1) == 1

    def test_the_clamped_helper_leaves_a_sane_value_alone(self, monkeypatch):
        monkeypatch.setenv("AUTOBOT_TTL_CLAMP_PROBE", "7200")

        from autobot_shared.env_utils import env_int_clamped

        assert env_int_clamped("AUTOBOT_TTL_CLAMP_PROBE", 86400, min_v=1) == 7200


class TestTheCountersAndTheirExpiryAreAtomic:
    """A counter must never be left without a TTL (#17380 review).

    `INCRBY` then `EXPIRE` as two round-trips has a real window: when the
    increment CREATES the key and the expiry then fails -- and
    `record_dev_loop_action` suppresses that failure -- the key is immortal. The
    counter never resets, so once the stored spend passes the ceiling every
    later action is refused until someone deletes the key by hand. A budget that
    silently becomes a permanent block is worse than one set too low, because
    nothing reports it.

    Redis preserves an existing expiry across an increment, so only the first
    write is exposed -- which is precisely the write that creates the key.

    These assert the TRANSACTION, not just the effect. "Both commands ran" is
    satisfied by the two-round-trip version; only "both commands were in one
    transaction" is not.
    """

    @pytest.mark.asyncio
    async def test_the_spend_increment_and_its_expiry_go_in_one_transaction(self, _reset_budget, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 1000)
        gate = token_budget.TokenBudgetGate()

        await gate.record_dev_loop_action(30)

        spend = [t for t in _reset_budget.transactions if any(c[1].endswith(":dev_loop") for c in t)]
        assert spend, f"no transaction touched the spend key; saw {_reset_budget.transactions}"
        commands = [c[0] for c in spend[0]]
        assert commands == [
            "incrby",
            "expire",
        ], f"the spend counter's increment and expiry were not one transaction: {commands}"

    @pytest.mark.asyncio
    async def test_the_hourly_rate_counter_is_atomic_too(self, _reset_budget, monkeypatch):
        """The review named only the spend counter; the rate counter had the
        identical shape, and an hour bucket left immortal blocks that bucket
        forever rather than for an hour."""
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 5)
        gate = token_budget.TokenBudgetGate()

        await gate.record_dev_loop_action(1)

        rate = [t for t in _reset_budget.transactions if any(":rate:" in c[1] for c in t)]
        assert rate, f"no transaction touched an hour bucket; saw {_reset_budget.transactions}"
        assert [c[0] for c in rate[0]] == ["incrby", "expire"]

    @pytest.mark.asyncio
    async def test_every_counter_written_also_got_an_expiry(self, _reset_budget, monkeypatch):
        """The property underneath both: no key is left immortal.

        Stated separately from the transaction shape because this is what the
        defect actually was -- a key with no TTL -- and it would still be worth
        asserting if the implementation moved to a Lua script instead.
        """
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 1000)
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 5)
        gate = token_budget.TokenBudgetGate()

        await gate.record_dev_loop_action(30)

        incremented = {c[1] for t in _reset_budget.transactions for c in t if c[0] == "incrby"}
        assert incremented, "nothing was incremented, so this asserts nothing"
        assert incremented <= set(
            _reset_budget.expired
        ), f"these counters were incremented with no expiry: {incremented - set(_reset_budget.expired)}"
        assert all(ttl >= 1 for ttl in _reset_budget.expired.values()), _reset_budget.expired
