# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot's dev-loop claim + budget gate (#17091 AC): a claimed issue is
skipped, the budget stops further actions, and the claim is released on
both success and failure -- proven against real Redis (fakeredis[lua],
work_claims needs real EVAL) and the real budget gate, not mocks of either.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from agents import dev_loop_issue_gate as gate_module
from agents.dev_loop_issue_gate import (
    DEV_LOOP_AGENT_ID,
    IssueBudgetExhausted,
    IssueClaimSkipped,
    run_dev_loop_action,
)
from autobot_shared.coordination import dev_loop_actions, work_claims
from autobot_shared.coordination.dev_loop_actions import (
    OUTCOME_FAILED,
    OUTCOME_RAN,
    OUTCOME_REFUSED_BUDGET,
    OUTCOME_SKIPPED_CLAIMED,
    last_refusal,
    recent,
)
from llm_shared import token_budget

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover - environment without the extra
    fakeredis_async = None


@pytest_asyncio.fixture
async def redis(monkeypatch):
    """One fakeredis server backing both work_claims (needs real EVAL) and
    the token-budget gate (plain get/incrby/expire)."""
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed — this gate needs real EVAL")
    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(work_claims, "get_async_redis_client", _client)
    # The action history shares the claims keyspace, so it shares the fake too.
    # Without this the recording silently no-ops and every assertion on it below
    # would pass by finding nothing -- which is the failure mode #17091 AC3 is
    # about, so it must not be the test harness's own behaviour.
    monkeypatch.setattr(dev_loop_actions, "get_async_redis_client", _client)
    monkeypatch.setattr(token_budget.TokenBudgetGate, "_get_redis", AsyncMock(return_value=client))
    yield client
    await client.flushall()


async def _ok_action() -> str:
    return "done"


async def _failing_action():
    raise ValueError("simulated action failure")


class TestClaimSkipping:
    """AC1: a claimed issue is skipped, never acted on."""

    @pytest.mark.asyncio
    async def test_an_unclaimed_issue_runs_the_action(self, redis):
        result = await run_dev_loop_action(4242, intent="verify ACs", estimated_tokens=1, action=_ok_action)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_an_issue_claimed_by_someone_else_is_skipped_not_run(self, redis):
        claimed = await work_claims.try_acquire(
            "issue:4242", agent_id="some-other-session", task_id="t-1", intent="already working this"
        )
        assert not isinstance(claimed, work_claims.ClaimConflict)

        ran = False

        async def _spy():
            nonlocal ran
            ran = True
            return "should not happen"

        result = await run_dev_loop_action(4242, intent="verify ACs", estimated_tokens=1, action=_spy)

        assert isinstance(result, IssueClaimSkipped)
        assert result.issue_number == 4242
        assert result.holder.holder.agent_id == "some-other-session"
        assert ran is False, "action must never run when the issue is already claimed"

    @pytest.mark.asyncio
    async def test_the_claim_does_not_outlive_a_successful_action(self, redis):
        await run_dev_loop_action(555, intent="verify ACs", estimated_tokens=1, action=_ok_action)

        claims = await work_claims.list_claims(kind="issue")
        assert not any(c.scope == "issue:555" for c in claims), "the claim must be released after success"


class TestBudgetStopsActions:
    """AC2/3: the budget is checked before the action, and stops it."""

    @pytest.mark.asyncio
    async def test_under_budget_the_action_runs(self, redis, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 1000)
        result = await run_dev_loop_action(1, intent="x", estimated_tokens=10, action=_ok_action)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_over_budget_the_action_never_runs(self, redis, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 10)
        ran = False

        async def _spy():
            nonlocal ran
            ran = True
            return "should not happen"

        result = await run_dev_loop_action(2, intent="x", estimated_tokens=1000, action=_spy)

        assert isinstance(result, IssueBudgetExhausted)
        assert result.issue_number == 2
        assert "token budget" in result.refusal.reason
        assert ran is False, "a budget refusal must never invoke the action (never partially posts)"

    @pytest.mark.asyncio
    async def test_a_budget_refusal_still_releases_the_claim(self, redis, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 10)

        await run_dev_loop_action(3, intent="x", estimated_tokens=1000, action=_ok_action)

        claims = await work_claims.list_claims(kind="issue")
        assert not any(c.scope == "issue:3" for c in claims), "a budget refusal must not leave the claim held"

    @pytest.mark.asyncio
    async def test_over_rate_budget_the_action_never_runs(self, redis, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_RATE_PER_HOUR", 1)
        await run_dev_loop_action(10, intent="x", estimated_tokens=1, action=_ok_action)

        ran = False

        async def _spy():
            nonlocal ran
            ran = True
            return "should not happen"

        result = await run_dev_loop_action(11, intent="x", estimated_tokens=1, action=_spy)

        assert isinstance(result, IssueBudgetExhausted)
        assert "rate budget" in result.refusal.reason
        assert ran is False


class TestClaimReleasedOnSuccessAndFailure:
    """AC1's other half: released on both success and failure."""

    @pytest.mark.asyncio
    async def test_released_after_a_successful_action(self, redis):
        await run_dev_loop_action(600, intent="x", estimated_tokens=1, action=_ok_action)
        claims = await work_claims.list_claims(kind="issue")
        assert not any(c.scope == "issue:600" for c in claims)

    @pytest.mark.asyncio
    async def test_released_after_a_failing_action(self, redis):
        with pytest.raises(ValueError, match="simulated action failure"):
            await run_dev_loop_action(601, intent="x", estimated_tokens=1, action=_failing_action)

        claims = await work_claims.list_claims(kind="issue")
        assert not any(
            c.scope == "issue:601" for c in claims
        ), "the claim must be released even though the action raised"

    @pytest.mark.asyncio
    async def test_a_failing_action_still_propagates_its_exception(self, redis):
        """The gate must not swallow the real error -- the caller needs to see it."""
        with pytest.raises(ValueError, match="simulated action failure"):
            await run_dev_loop_action(602, intent="x", estimated_tokens=1, action=_failing_action)


class TestClaimIdentity:
    @pytest.mark.asyncio
    async def test_the_dev_loop_claims_under_its_own_agent_id(self, redis):
        seen_agent_id = None

        async def _capture():
            nonlocal seen_agent_id
            claims = await work_claims.list_claims(kind="issue")
            seen_agent_id = next(c.agent_id for c in claims if c.scope == "issue:700")
            return "ok"

        await run_dev_loop_action(700, intent="x", estimated_tokens=1, action=_capture)

        assert seen_agent_id == DEV_LOOP_AGENT_ID


class TestTheActionIsRecorded:
    """AC2/AC3: every attempt is recorded per action, including the refused ones.

    A running total answers "may the next action run". It cannot answer "what
    did the loop do and why did it stop", which is what AC3's *records why, and
    surfaces it* needs -- and a refusal that leaves no trace is indistinguishable
    from an action nobody attempted.
    """

    @pytest.mark.asyncio
    async def test_a_successful_action_is_recorded_with_its_cost(self, redis):
        await run_dev_loop_action(17091, intent="verify ACs", estimated_tokens=1234, action=_ok_action)

        entries = await recent(17091)
        assert [e.outcome for e in entries] == [OUTCOME_RAN]
        assert entries[0].estimated_tokens == 1234
        assert entries[0].intent == "verify ACs"
        assert entries[0].reason == ""

    @pytest.mark.asyncio
    async def test_a_skipped_issue_is_recorded_with_its_holder(self, redis):
        await work_claims.try_acquire(
            "issue:17091",
            agent_id="another-session",
            task_id="t1",
            mode=work_claims.ClaimMode.EXCLUSIVE,
            intent="already working it",
        )

        await run_dev_loop_action(17091, intent="verify ACs", estimated_tokens=10, action=_ok_action)

        entries = await recent(17091)
        assert [e.outcome for e in entries] == [OUTCOME_SKIPPED_CLAIMED]
        assert "another-session" in entries[0].reason

    @pytest.mark.asyncio
    async def test_a_budget_refusal_is_recorded_with_the_reason(self, redis, monkeypatch):
        monkeypatch.setattr(token_budget, "DEV_LOOP_TOKEN_BUDGET", 100)

        result = await run_dev_loop_action(17091, intent="verify ACs", estimated_tokens=500, action=_ok_action)

        assert isinstance(result, IssueBudgetExhausted)
        entries = await recent(17091)
        assert [e.outcome for e in entries] == [OUTCOME_REFUSED_BUDGET]
        assert "budget exhausted" in entries[0].reason
        assert last_refusal(entries) is entries[0]

    @pytest.mark.asyncio
    async def test_a_failing_action_is_recorded_as_failed_not_as_ran(self, redis):
        with pytest.raises(ValueError):
            await run_dev_loop_action(17091, intent="verify ACs", estimated_tokens=7, action=_failing_action)

        entries = await recent(17091)
        assert [e.outcome for e in entries] == [OUTCOME_FAILED]
        assert entries[0].estimated_tokens == 7

    @pytest.mark.asyncio
    async def test_the_history_is_newest_first_across_several_attempts(self, redis):
        await run_dev_loop_action(17091, intent="first", estimated_tokens=1, action=_ok_action)
        await run_dev_loop_action(17091, intent="second", estimated_tokens=2, action=_ok_action)

        entries = await recent(17091)
        assert [e.intent for e in entries] == ["second", "first"]

    @pytest.mark.asyncio
    async def test_an_untouched_issue_has_an_empty_history_not_an_error(self, redis):
        """Nothing found, from a reachable store -- the other half of AC3's
        distinction. `recent` raises when Redis is unavailable instead."""
        assert await recent(4242) == []


class TestAFailingReleaseDoesNotMaskTheAction:
    """A review finding: `release` reaches Redis and can raise.

    Raised from inside the outer `finally` it would REPLACE the exception
    already propagating from the action, so the caller would be told the release
    failed and never told what actually went wrong.
    """

    @pytest.mark.asyncio
    async def test_the_actions_own_exception_still_reaches_the_caller(self, redis, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("redis went away at release time")

        monkeypatch.setattr(gate_module, "release", _boom)

        with pytest.raises(ValueError, match="simulated action failure"):
            await run_dev_loop_action(17091, intent="verify", estimated_tokens=1, action=_failing_action)

    @pytest.mark.asyncio
    async def test_a_successful_action_still_returns_its_value(self, redis, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("redis went away at release time")

        monkeypatch.setattr(gate_module, "release", _boom)

        assert await run_dev_loop_action(17091, intent="verify", estimated_tokens=1, action=_ok_action) == "done"

    @pytest.mark.asyncio
    async def test_a_renewal_that_dies_badly_does_not_skip_the_release(self, redis, monkeypatch):
        """`await renewal_task` re-raises whatever it ended with; anything other
        than CancelledError would have skipped the release entirely."""
        released: list[str] = []

        async def _renew_boom(scope, *, task_id, lost):
            raise RuntimeError("renewal died")

        async def _record_release(scope, *, agent_id, task_id):
            released.append(scope)
            return True

        monkeypatch.setattr(gate_module, "_renew_forever", _renew_boom)
        monkeypatch.setattr(gate_module, "release", _record_release)

        assert await run_dev_loop_action(17091, intent="verify", estimated_tokens=1, action=_ok_action) == "done"
        assert released == ["issue:17091"], "the claim must be released even when the renewal task dies"
