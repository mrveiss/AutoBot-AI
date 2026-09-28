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
    _IDLE_WAKE_AT_KEY,
    _IDLE_WAKE_COUNT_KEY,
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

    redis.hincrby.assert_awaited_once_with(_IDLE_WAKE_COUNT_KEY, _AGENT_SLUG, 1)
    assert redis.hset.await_args[0][0] == _IDLE_WAKE_AT_KEY
    assert redis.hset.await_args[0][1] == _AGENT_SLUG
    assert redis.expire.await_count == 2


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
