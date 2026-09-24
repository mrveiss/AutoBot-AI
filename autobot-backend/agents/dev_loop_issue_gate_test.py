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

import asyncio
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
    OUTCOME_RAN_CLAIM_LAPSED,
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


class TestCancellationIsAnExitPathToo:
    """The fourth exit path: the caller cancels while the action is in flight.

    The other three -- normal return, the action raising, and the renewal task
    raising something other than `CancelledError` -- each have their own test
    above. Cancellation is the one that had none, and it is the least like the
    others: the release sits in a `finally` and reaches Redis with an `await`,
    and an `await` inside a `finally` on a cancelled task is exactly where
    cleanup gets skipped. A leaked EXCLUSIVE claim locks the issue until its
    lease TTL expires, so this is the path where a leak costs the most.

    What the FIRST test does and does not prove, because the difference matters.
    It proves the release is reached and completes: deleting the release from the
    outer `finally` fails it. It does NOT prove much about suspension, because
    `fakeredis` answers without yielding to the event loop -- inserting an
    `await asyncio.sleep(0)` before the release, and even a second
    `current_task().cancel()` in front of it, both leave it passing. A release
    that never suspends can never be interrupted, so the risky shape was
    untested by it.

    The second test is the one that covers that shape: a release that suspends
    before it records. That is the real client's behaviour and the only version
    where "an await inside a finally on a cancelled task" can actually bite.
    """

    @pytest.mark.asyncio
    async def test_a_cancelled_action_still_releases_the_claim(self, redis):
        running = asyncio.Event()

        async def _slow_action():
            running.set()
            await asyncio.sleep(60)

        task = asyncio.create_task(run_dev_loop_action(17093, intent="verify", estimated_tokens=1, action=_slow_action))
        await running.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        claims = await work_claims.list_claims(kind="issue")
        assert not any(c.scope == "issue:17093" for c in claims), (
            "cancelling the caller leaked the claim: issue:17093 is still held, and stays held "
            "until the lease TTL expires"
        )

    @pytest.mark.asyncio
    async def test_a_release_that_suspends_still_completes_under_cancellation(self, redis, monkeypatch):
        """The shape `fakeredis` cannot exercise: a release that yields first.

        A real Redis client suspends on the socket, so the release's `await` is
        a real suspension point inside a `finally` on a cancelled task. This
        substitutes a release that yields before it records, which is the
        minimum needed to tell "the release was attempted" from "the release
        finished".
        """
        released: list[str] = []
        running = asyncio.Event()

        async def _suspending_release(scope, *, agent_id, task_id):
            await asyncio.sleep(0)
            released.append(scope)
            return True

        async def _slow_action():
            running.set()
            await asyncio.sleep(60)

        monkeypatch.setattr(gate_module, "release", _suspending_release)

        task = asyncio.create_task(run_dev_loop_action(17094, intent="verify", estimated_tokens=1, action=_slow_action))
        await running.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert released == ["issue:17094"], (
            "the release suspended and never finished: cancelling the caller leaks the claim "
            "whenever the Redis call yields, which is every real client"
        )


class TestALapsedClaimIsNotACleanRun:
    """A run whose exclusive claim lapsed gets its own outcome (#17380 review).

    `_renew_forever` records the loss and returns; the action deliberately keeps
    running, because cancelling it mid-write is how "never partially posts"
    gets broken. But the run is then recorded as OUTCOME_RAN with the lapse
    appended to a free-text `reason` -- and nothing queries free text. Any
    history query for clean runs returned a run another agent could have been
    acting alongside, which is the collision the claim exists to prevent made
    invisible after the fact.

    The lapse was recorded and untested, which is why a reviewer found it and
    the suite did not.
    """

    @staticmethod
    def _lapsing_renewal(monkeypatch):
        """Substitute the renewal at its real seam: the gate still calls this.

        Returns an event the action must await. Without it the test is a race it
        usually loses: the gate creates the renewal task and then awaits the
        budget check, so an action that returns immediately reaches the
        `finally` before the renewal coroutine has had its first step and
        `claim_lost` is still empty. The first version of this test failed for
        that reason and not because the code was wrong -- ordering asserted
        with an event rather than hoped for with a sleep.
        """
        lapsed = asyncio.Event()

        async def _renew_lapsed(scope, *, task_id, lost):
            lost.append("the claim lapsed mid-action: another agent could have acquired this issue")
            lapsed.set()

        monkeypatch.setattr(gate_module, "_renew_forever", _renew_lapsed)
        return lapsed

    @staticmethod
    def _action_awaiting(lapsed):
        async def _action():
            await lapsed.wait()
            return "done"

        return _action

    @pytest.mark.asyncio
    async def test_a_successful_action_whose_claim_lapsed_is_not_recorded_as_ran(self, redis, monkeypatch):
        lapsed = self._lapsing_renewal(monkeypatch)

        result = await run_dev_loop_action(
            17380, intent="verify", estimated_tokens=1, action=self._action_awaiting(lapsed)
        )
        assert result == "done"

        entry = (await recent(17380))[0]
        assert entry.outcome == OUTCOME_RAN_CLAIM_LAPSED, (
            f"recorded {entry.outcome!r}: a history query for clean runs would return a run whose "
            "exclusivity was lost"
        )

    @pytest.mark.asyncio
    async def test_the_reason_still_names_the_lapse(self, redis, monkeypatch):
        """The outcome is queryable; the reason is what a human reads."""
        lapsed = self._lapsing_renewal(monkeypatch)

        await run_dev_loop_action(17381, intent="verify", estimated_tokens=1, action=self._action_awaiting(lapsed))

        assert "lapsed" in (await recent(17381))[0].reason

    @pytest.mark.asyncio
    async def test_a_failing_action_keeps_failed_even_when_the_claim_lapsed(self, redis, monkeypatch):
        """Only an otherwise-clean run is relabelled -- a raised action is the
        more serious fact and must not be softened into a lapse."""
        lapsed = self._lapsing_renewal(monkeypatch)

        async def _fails_after_the_lapse():
            await lapsed.wait()
            raise ValueError("simulated action failure")

        with pytest.raises(ValueError, match="simulated action failure"):
            await run_dev_loop_action(17382, intent="verify", estimated_tokens=1, action=_fails_after_the_lapse)

        assert (await recent(17382))[0].outcome == OUTCOME_FAILED

    @pytest.mark.asyncio
    async def test_a_run_whose_claim_held_is_still_recorded_as_ran(self, redis):
        """Negative control: without a lapse the outcome must not change.

        Without this, the assertions above pass equally well against a gate that
        labelled every run `ran_claim_lapsed`.
        """
        await run_dev_loop_action(17383, intent="verify", estimated_tokens=1, action=_ok_action)

        assert (await recent(17383))[0].outcome == OUTCOME_RAN
