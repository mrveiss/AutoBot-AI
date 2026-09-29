# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A heartbeat wake with nothing to do costs nothing, and still leaves a trace (#17726).

The trace is the part that makes the feature safe rather than merely cheap. With
no ``llc_heartbeat_runs`` row written, "the queue was empty" and "the scheduler
is dead" are the same observation from the runs table -- and at a one-minute
cron that is 1,440 indistinguishable silences per agent per day. So the tests
below assert both halves: nothing was spent, and something was recorded.

Parent: #15907, whose owner ruling made the one-minute cadence conditional on
this landing first.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.work_item import LLCWorkItem
from llc.scheduler.heartbeat_scheduler import (
    _IDLE_WAKE_KEY_PREFIX,
    _IDLE_WAKE_TTL_SECONDS,
    HeartbeatScheduler,
)

_AGENT_SLUG = "ceo-acme"
_NODE_ID = str(uuid.uuid4())
_COMPANY_ID = str(uuid.uuid4())
_HBS = "llc.scheduler.heartbeat_scheduler"


def _make_agent(**over: Any) -> Dict[str, Any]:
    agent = {
        "agent_id": _AGENT_SLUG,
        "agent_node_id": _NODE_ID,
        "company_id": _COMPANY_ID,
        "name": "Acme CEO",
        "heartbeat_cron": "* * * * *",
        "heartbeat_enabled": True,
        "adapter_type": "claude_code",
        "adapter_config": {},
        "context_mode": "slim",
    }
    agent.update(over)
    return agent


def _make_redis() -> MagicMock:
    redis = MagicMock()
    for name in ("zadd", "zrem", "hincrby", "hset", "expire"):
        setattr(redis, name, AsyncMock())
    return redis


def _make_session() -> MagicMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_run() -> MagicMock:
    run = MagicMock()
    run.id = uuid.uuid4()
    run.context_snapshot = None
    run.retry_count = 0
    return run


async def _drive(*, has_work: bool, agent: Dict[str, Any] | None = None, rate_limited=None, redis=None):
    """Run one due-agent tick and hand back what it touched."""
    scheduler = HeartbeatScheduler()
    redis = redis or _make_redis()
    create_run = AsyncMock(return_value=_make_run())
    run_adapter = AsyncMock()
    with (
        patch.object(scheduler, "_get_agent_config", AsyncMock(return_value=agent or _make_agent())),
        patch.object(scheduler, "_find_rate_limited_run", AsyncMock(return_value=rate_limited)),
        patch.object(scheduler, "_create_run", create_run),
        patch.object(scheduler, "_run_adapter", run_adapter),
        patch(f"{_HBS}.has_pending_work", AsyncMock(return_value=has_work)),
        patch(f"{_HBS}.get_async_session_factory", return_value=_make_session()),
    ):
        await scheduler._handle_due_agent(_AGENT_SLUG, redis)
    return scheduler, redis, create_run, run_adapter


# ---------------------------------------------------------------------------
# The spend, or the absence of it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_empty_queue_writes_no_run_and_calls_no_adapter():
    """The whole point: no run row, no adapter call, no model invocation."""
    _, _, create_run, run_adapter = await _drive(has_work=False)

    create_run.assert_not_called()
    run_adapter.assert_not_called()


@pytest.mark.asyncio
async def test_a_non_empty_queue_dispatches_exactly_as_before():
    """The contrast case. Without it, "cheap" is satisfied by never running."""
    _, _, create_run, run_adapter = await _drive(has_work=True)

    create_run.assert_called_once()
    run_adapter.assert_called_once()


@pytest.mark.asyncio
async def test_a_rate_limited_run_resumes_even_when_the_queue_looks_empty():
    """A resumed run already holds a checked-out item, so the queue is silent about it.

    If the short-circuit ran first, a rate-limited agent would never retry: its
    work is checked out, so `has_pending_work` is False *because* it has work.
    """
    rate_limited = _make_run()
    rate_limited.context_snapshot = {"work_item_id": "abc"}

    _, _, create_run, run_adapter = await _drive(has_work=False, rate_limited=rate_limited)

    create_run.assert_not_called()  # resumed, not re-created
    run_adapter.assert_called_once()
    assert run_adapter.call_args[0][2] == {"work_item_id": "abc"}


@pytest.mark.asyncio
async def test_an_agent_the_check_cannot_resolve_is_dispatched_as_before():
    """Fail open. A wrong "no work" drops work; a wrong "work" costs one wake."""
    _, _, create_run, run_adapter = await _drive(has_work=False, agent=_make_agent(agent_node_id=None))

    create_run.assert_called_once()
    run_adapter.assert_called_once()


# ---------------------------------------------------------------------------
# The trace: found-nothing must not look like did-not-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_short_circuited_wake_records_a_count_and_a_timestamp():
    """The AC that decides whether the feature is safe, not just cheap."""
    _, redis, _, _ = await _drive(has_work=False)

    key = f"{_IDLE_WAKE_KEY_PREFIX}{_AGENT_SLUG}"
    redis.hincrby.assert_awaited_once_with(key, "count", 1)
    assert redis.hset.await_args[0][0] == key
    assert redis.hset.await_args[0][1] == "at"
    # ONE expire, on this agent's own key, so the TTL covers this agent alone.
    # Re-expiring a shared hash kept every idle agent's row alive for as long as
    # any agent stayed busy -- the documented retention, inverted (review).
    redis.expire.assert_awaited_once_with(key, int(_IDLE_WAKE_TTL_SECONDS))


@pytest.mark.asyncio
async def test_a_short_circuited_wake_still_advances_the_schedule():
    """Forget this and the agent goes quiet forever -- the worst failure here."""
    _, redis, _, _ = await _drive(has_work=False)

    redis.zadd.assert_awaited_once()
    assert redis.zadd.await_args[0][1].get(_AGENT_SLUG) is not None
    redis.zrem.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_bookkeeping_failure_does_not_cost_the_schedule_advance():
    """Redis may fail. A free wake must not become a stopped agent."""
    redis = _make_redis()
    redis.hincrby = AsyncMock(side_effect=RuntimeError("redis down"))

    _, redis, create_run, _ = await _drive(has_work=False, redis=redis)

    redis.zadd.assert_awaited_once()
    create_run.assert_not_called()


@pytest.mark.asyncio
async def test_an_invalid_cron_drops_the_agent_rather_than_rescheduling_it():
    """The short-circuit reuses the dispatch path's cron handling, not a copy."""
    redis = _make_redis()
    _, redis, _, _ = await _drive(has_work=False, agent=_make_agent(heartbeat_cron="not a cron"), redis=redis)

    redis.zrem.assert_awaited_once_with("llc:heartbeat:schedule", _AGENT_SLUG)
    redis.zadd.assert_not_awaited()


# ---------------------------------------------------------------------------
# One definition of "next work"
# ---------------------------------------------------------------------------


class _RecordingSession:
    """Captures the statements executed, and offers nothing."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement, *_a, **_k):
        self.statements.append(statement)
        result = MagicMock()
        result.first.return_value = None
        scalars = MagicMock()
        scalars.all.return_value = []
        result.scalars.return_value = scalars
        return result


@pytest.mark.asyncio
async def test_the_emptiness_check_filters_on_the_same_rule_as_the_checkout():
    """AC: "next work" has one definition, asserted on the queries actually issued.

    Not by reading the source and not by comparing two hand-built queries --
    both of those pass while the real calls diverge. These are the statements
    ``has_pending_work`` and ``checkout_next`` hand to the session.
    """
    from llc.services.work_item_queue import checkout_next, has_pending_work

    probe = _RecordingSession()
    await has_pending_work(probe, _NODE_ID, _COMPANY_ID)

    claim = _RecordingSession()
    await checkout_next(claim, MagicMock(), _NODE_ID, _COMPANY_ID)

    assert len(probe.statements) == 1 and len(claim.statements) == 1

    def _sql(clause) -> str:
        # Compiled, not repr()'d: a clause's repr carries its memory address, so
        # comparing reprs compares object identity and fails on equal queries.
        return str(clause.compile(compile_kwargs={"literal_binds": True}))

    assert _sql(probe.statements[0].whereclause) == _sql(claim.statements[0].whereclause)
    assert [_sql(c) for c in probe.statements[0]._order_by_clauses] == [
        _sql(c) for c in claim.statements[0]._order_by_clauses
    ]


@pytest.mark.asyncio
async def test_the_emptiness_check_is_bounded_to_one_row():
    """Cheap by construction, not by the backlog happening to be short."""
    from llc.services.work_item_queue import has_pending_work

    probe = _RecordingSession()
    await has_pending_work(probe, _NODE_ID, _COMPANY_ID)

    statement = probe.statements[0]
    assert statement._limit == 1
    # The id, not the entity: nothing is instantiated to answer a yes/no.
    assert [c.name for c in statement.selected_columns] == [LLCWorkItem.id.name]


# ---------------------------------------------------------------------------
# #15907's other half: the cadence the short-circuit makes affordable
# ---------------------------------------------------------------------------


def test_a_hire_defaults_to_a_one_minute_cron():
    """Before this, heartbeat_enabled=true with no cron was silently unschedulable."""
    from llc.api.agent_hires import DEFAULT_HEARTBEAT_CRON, AgentHireRequest

    assert DEFAULT_HEARTBEAT_CRON == "* * * * *"
    assert AgentHireRequest(agent_name="CEO").heartbeat_cron == DEFAULT_HEARTBEAT_CRON


def test_a_hire_still_has_to_opt_into_the_heartbeat():
    """Option A from the ruling was rejected: a cadence is not an opt-in."""
    from llc.api.agent_hires import AgentHireRequest

    assert AgentHireRequest(agent_name="CEO").heartbeat_enabled is False


def test_an_explicit_cron_still_wins():
    from llc.api.agent_hires import AgentHireRequest

    assert AgentHireRequest(agent_name="CEO", heartbeat_cron="0 * * * *").heartbeat_cron == "0 * * * *"


class TestAMisconfiguredCronDoesNotSilentlyUnscheduleAgents:
    """The inverse of this change's thesis (#17726 review).

    The idle short-circuit exists so a wake that finds nothing still leaves a
    trace. An agent that never wakes **at all** must not leave less of one --
    and two paths made exactly that happen.
    """

    def test_a_malformed_configured_default_falls_back_loudly(self, monkeypatch, caplog):
        """An unvalidated env value persisted into every opt-in hire.

        The scheduler answers a bad cron with `warning(); continue`, so the agent
        is stored with `heartbeat_enabled=true`, never enters the schedule and
        never wakes. One warning per repopulate is the only evidence.
        """
        import importlib
        import logging

        monkeypatch.setenv("AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON", "not a cron at all")
        with caplog.at_level(logging.ERROR):
            module = importlib.reload(importlib.import_module("llc.api.agent_hires"))

        assert module.DEFAULT_HEARTBEAT_CRON == "* * * * *", (
            "a malformed configured default was accepted; every agent hired with "
            "heartbeat_enabled=true would be stored unschedulable"
        )
        # getMessage(), not .message: the latter is the raw format string, so a
        # naive `in` check tests the template rather than the interpolated value.
        assert any("not a cron at all" in r.getMessage() for r in caplog.records), (
            "the rejected value is not named in any log record -- an operator cannot fix " "what the log does not quote"
        )

        monkeypatch.delenv("AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON", raising=False)
        importlib.reload(module)

    def test_a_valid_configured_default_is_honoured(self, monkeypatch):
        """The contrast case, and the first version did not contrast.

        It asserted `_validated_default_cron() == "* * * * *"` without setting
        the env var -- comparing the fallback against the fallback. It would have
        passed a validator that rejected every non-default cron. A contrast case
        sharing the subject's inputs is not one (review).
        """
        import llc.api.agent_hires as mod

        monkeypatch.setenv("AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON", "*/15 * * * *")
        assert mod._validated_default_cron() == "*/15 * * * *"

    async def test_one_bad_cron_does_not_unschedule_everyone(self):
        """`_next_fire` raises RuntimeError with croniter absent, and the loop caught
        only `(ValueError, KeyError)` -- so it escaped `_repopulate_schedule` and
        `start()`, which has no handler. One missing dependency took out scheduling
        for every agent instead of skipping one.

        Pinned here rather than in a comment, because a comment cannot fail when
        somebody narrows the handler back to be tidy.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

        scheduler = HeartbeatScheduler()
        redis = _make_redis()
        agents = [
            {"agent_id": "bad", "heartbeat_cron": "* * * * *"},
            {"agent_id": "good", "heartbeat_cron": "* * * * *"},
        ]

        calls = {"n": 0}

        def _fire(cron_expr, now):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("croniter is required for heartbeat scheduling")
            return now + 60.0

        with (
            patch.object(scheduler, "_load_enabled_agents", AsyncMock(return_value=agents)),
            patch.object(scheduler, "_restore_rate_limited_agents", AsyncMock()),
            patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=redis)),
            patch(f"{_HBS}._next_fire", MagicMock(side_effect=_fire)),
        ):
            await scheduler._repopulate_schedule()

        assert calls["n"] == 2, "the loop stopped at the first failure instead of continuing"
        redis.zadd.assert_awaited()
        scheduled = redis.zadd.await_args[0][1]
        assert "good" in scheduled and "bad" not in scheduled

    def test_a_syntactically_valid_cron_that_can_never_fire_is_rejected(self, monkeypatch):
        """Construction proves the syntax; a fire proves the schedule (review).

        `0 0 31 2 *` constructs without error -- February has no 31st, so it can
        never fire. Validating by construction alone accepted it, producing
        exactly the silently-dead agent the validator exists to prevent: stored
        `heartbeat_enabled=true`, never scheduled, one warning per repopulate.
        """
        import llc.api.agent_hires as mod

        monkeypatch.setenv("AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON", "0 0 31 2 *")
        assert mod._validated_default_cron() == "* * * * *"

    def test_the_idle_wake_ttl_cannot_be_configured_to_zero(self):
        """A TTL of 0 deletes the only evidence a short-circuited wake happened.

        This PR's premise is that a wake finding nothing still leaves a trace, so
        a tuning knob must not be able to erase it. `env_float_clamped` floors it
        AND logs the rejected value -- a silent correction is indistinguishable
        from a value that was honoured (#15778's reasoning, reused rather than
        rewritten).
        """
        import re
        from pathlib import Path

        from llc.scheduler import heartbeat_scheduler as mod

        # Asserted against the CALL SITE, not by calling the helper.
        #
        # The first two versions of this test were both worthless, in the same
        # way twice. The first never set the probe variable, so the helper
        # returned its default and `>= 60` passed without exercising the clamp.
        # The second set it -- and still only proved that `env_float_clamped`
        # clamps, which is `autobot_shared`'s test to own. Reverting THIS module
        # to a bare `env_float` left both of them green.
        #
        # What drifted is which helper this constant is built with, so that is
        # what is pinned. A reload with a hostile env would be behavioural, but it
        # re-executes this module's singletons mid-suite and the patch targets
        # other tests here rely on.
        src = Path(mod.__file__).read_text(encoding="utf-8")
        line = next(
            (ln for ln in src.splitlines() if "AUTOBOT_LLC_HEARTBEAT_IDLE_WAKE_TTL_SECONDS" in ln and "=" in ln),
            None,
        )
        assert line, "the idle-wake TTL constant is gone"
        assert "env_float_clamped" in line, (
            f"the idle-wake TTL is read with an unclamped helper: {line.strip()!r}. A configured 0 or "
            "negative then deletes the only evidence a short-circuited wake happened."
        )
        assert re.search(r"min_v\s*=\s*[1-9]", line), f"no positive floor on the idle-wake TTL: {line.strip()!r}"
