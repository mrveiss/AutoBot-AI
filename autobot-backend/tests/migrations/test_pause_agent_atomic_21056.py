# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``ControlsService.pause_agent`` is one conditional UPDATE, so a racing writer cannot undo it (#21056, #21190).

The unit tests use a fake session, which cannot show a race. Here real sessions contend for one
``agent_org_nodes`` row. A holder keeps its transaction open, the racer is seen waiting through
``pg_blocking_pids`` (the wait is polled to a deadline, it is never the ordering), then the holder commits:

* terminate holds, pause waits: the pause is refused and the agent ends TERMINATED, with the terminate reason
  and Redis flag intact (never PAUSED-after-TERMINATED);
* a first pause holds, a second waits: exactly one wins; the other is recorded as a repeat no-op and the
  first reason and ``pre_pause_status`` stay;
* ``asyncio.gather`` of a pause and a terminate, and of two pauses, ends in the same states whatever the order.

Real Postgres only (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic
from tests.migrations.test_membership_lock_19985 import _backend_pid, _wait_until_blocked_on

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

ACTOR = str(uuid.uuid4())


class _Log:
    """Records the event types; the activity table is not what is under test."""

    def __init__(self) -> None:
        self.events: list = []

    async def record(self, **kw) -> None:  # noqa: ANN003
        self.events.append(kw["event_type"].value)


@pytest.fixture()
async def maker(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url, pool_size=8)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
def flags(monkeypatch):
    """The Redis flag per agent, as the service last set it."""
    store: dict = {}

    async def _set(key, value, *a, **k):  # noqa: ANN002, ANN003
        store[key] = value

    client = SimpleNamespace(set=_set)

    async def _client():
        return client

    monkeypatch.setattr("llc.services.controls_service.get_async_redis_client", _client)
    return store


async def _seed(maker, status="available"):  # noqa: ANN001
    from models.agent_org import AgentOrgNode

    company, slug = str(uuid.uuid4()), f"bot-{uuid.uuid4().hex[:8]}"
    async with maker() as session:
        session.add(
            AgentOrgNode(id=uuid.uuid4(), agent_id=slug, name="Bot", company_id=uuid.UUID(company), status=status)
        )
        await session.commit()
    return company, slug


async def _row(maker, company, slug) -> tuple:  # noqa: ANN001
    sql = "SELECT status, pause_reason, pre_pause_status FROM agent_org_nodes WHERE agent_id = :s"
    async with maker() as session:
        return tuple((await session.execute(sa.text(sql), {"s": slug})).one())


async def _pause(maker, svc, company, slug, reason, *, session=None, commit=True):  # noqa: ANN001
    async def run(s):  # noqa: ANN001
        out = await svc.pause_agent(s, company, slug, ACTOR, reason=reason)
        if commit:
            await s.commit()
        return out

    if session is not None:
        return await run(session)
    async with maker() as s:
        return await run(s)


async def _terminate(maker, svc, company, slug, reason="fired", *, session=None, commit=True):  # noqa: ANN001
    async def run(s):  # noqa: ANN001
        out = await svc.terminate_agent(s, company, slug, ACTOR, reason=reason)
        if commit:
            await s.commit()
        return out

    if session is not None:
        return await run(session)
    async with maker() as s:
        return await run(s)


async def _hold_then_race(maker, hold, racer):  # noqa: ANN001
    """Session A runs *hold* uncommitted; *racer* starts and is seen waiting on A; A commits; return racer's outcome."""
    async with maker() as a:
        await hold(a)
        pid = await _backend_pid(a)
        task = asyncio.create_task(racer())
        try:
            await _wait_until_blocked_on(maker, pid, task)
            await a.commit()
            return await asyncio.gather(task, return_exceptions=True)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_pause_waiting_on_a_terminate_is_refused_and_the_agent_stays_terminated(maker, flags):
    from llc.services.controls_service import AgentNotPausableError, ControlsService

    log = _Log()
    svc = ControlsService(activity_log=log)
    company, slug = await _seed(maker)

    [outcome] = await _hold_then_race(
        maker,
        lambda a: _terminate(maker, svc, company, slug, session=a, commit=False),
        lambda: _pause(maker, svc, company, slug, "hold"),
    )

    assert isinstance(outcome, AgentNotPausableError)
    assert await _row(maker, company, slug) == ("terminated", "fired", None)
    assert flags[f"llc:agent:{slug}:paused"] == "terminated"
    assert log.events == ["control.agent_terminated"]


async def test_second_first_pause_waiting_on_the_first_is_a_recorded_repeat(maker, flags):
    from llc.services.controls_service import ControlsService

    log = _Log()
    svc = ControlsService(activity_log=log)
    company, slug = await _seed(maker, status="in_sprint")

    [outcome] = await _hold_then_race(
        maker,
        lambda a: _pause(maker, svc, company, slug, "operator", session=a, commit=False),
        lambda: _pause(maker, svc, company, slug, "quota"),
    )

    assert outcome["already_paused"] is True and outcome["pause_reason"] == "operator"
    assert await _row(maker, company, slug) == ("paused", "operator", "in_sprint")
    assert log.events == ["control.agent_paused", "control.agent_pause_repeated"]
    assert flags[f"llc:agent:{slug}:paused"] == "1"


async def test_gathered_pause_and_terminate_always_end_terminated(maker, flags):
    from llc.services.controls_service import AgentNotPausableError, ControlsService

    svc = ControlsService(activity_log=_Log())
    for _ in range(5):
        company, slug = await _seed(maker)
        results = await asyncio.gather(
            _pause(maker, svc, company, slug, "hold"),
            _terminate(maker, svc, company, slug),
            return_exceptions=True,
        )
        assert [r for r in results if isinstance(r, Exception) and not isinstance(r, AgentNotPausableError)] == []
        assert (await _row(maker, company, slug))[0] == "terminated"


async def test_gathered_first_pauses_one_wins_and_the_other_is_a_repeat(maker, flags):
    from llc.services.controls_service import ControlsService

    log = _Log()
    svc = ControlsService(activity_log=log)
    company, slug = await _seed(maker)

    results = await asyncio.gather(_pause(maker, svc, company, slug, "one"), _pause(maker, svc, company, slug, "two"))

    winners = [r for r in results if not r.get("already_paused")]
    assert len(winners) == 1 and sum(1 for r in results if r.get("already_paused")) == 1
    status, reason, before = await _row(maker, company, slug)
    assert (status, reason, before) == ("paused", winners[0]["pause_reason"], "available")
    assert sorted(log.events) == ["control.agent_pause_repeated", "control.agent_paused"]
