# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19582 review (PR #19598): a stale run never blocks, and a wake never fails the write.

* A QUEUED or RUNNING row older than the stalled-run sweep's deadline (left by a crash
  or restart) does not count as the agent being busy: a new run still claims RUNNING
  and an event still wakes the agent. A fresh one still blocks both.
* An agent ``trigger_manual`` refuses, and a ``dispatch_run`` that raises after
  commit, are logged; the user's comment or assignment write still succeeds.

The per-agent claim lock itself needs real row locks:
``tests/migrations/test_run_claim_lock_19582.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from llc.models.enums import LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.models.work_item import LLCWorkItem
from llc.scheduler import stalled_run_sweep
from llc.scheduler.heartbeat_scheduler import LLCHeartbeatScheduler
from llc.scheduler.run_status import RunSuperseded, mark_running
from llc.tests import test_event_wakes_19582 as base
from llc.tests.test_event_wakes_19582 import _COMPANY, _agent, _assign, _item, _runs, _update_assignee
from models.agent_org import AgentOrgNode

pytestmark = pytest.mark.asyncio

#: The sibling module's fixtures: the same in-memory schema and dispatch recorder.
factory, dispatched = base.factory, base.dispatched

#: Ages either side of the sweep's deadline: a minute past it, and a minute old.
_STALE = timedelta(seconds=stalled_run_sweep.STALL_TIMEOUT_SECONDS + 60)
_FRESH = timedelta(seconds=60)


async def _old_run(factory, node: AgentOrgNode, status: str, age: timedelta) -> uuid.UUID:  # noqa: ANN001
    """A tick's run of *node*, *age* old: started then for RUNNING, created then for QUEUED."""
    then = datetime.now(timezone.utc) - age
    started = then if status == LLCRunStatus.RUNNING.value else None
    async with factory() as session:
        run = LLCHeartbeatRun(
            id=uuid.uuid4(),
            company_id=_COMPANY,
            agent_id=node.agent_id,
            invocation_source="scheduler",
            status=status,
            started_at=started,
            created_at=then,
        )
        session.add(run)
        await session.commit()
        return run.id


async def _queued_run(factory, node: AgentOrgNode) -> uuid.UUID:  # noqa: ANN001
    return await _old_run(factory, node, LLCRunStatus.QUEUED.value, timedelta(0))


# -- HIGH 2: staleness is bounded by the sweep's deadline ---------------------------------


@pytest.mark.parametrize("status", [LLCRunStatus.RUNNING.value, LLCRunStatus.QUEUED.value])
@pytest.mark.parametrize(("age", "blocks"), [(_STALE, False), (_FRESH, True)], ids=["stale", "fresh"])
async def test_only_a_live_run_blocks_a_wake(
    factory, dispatched, status: str, age: timedelta, blocks: bool  # noqa: ANN001
) -> None:
    node = await _agent(factory)
    leftover = await _old_run(factory, node, status, age)
    await _assign(factory, node)
    woken = [r.id for r in await _runs(factory, node.agent_id) if r.id != leftover]
    assert (woken == []) is blocks, f"a {status} run aged {age} must {'' if blocks else 'not '}block a wake"
    assert (dispatched == []) is blocks


@pytest.mark.parametrize(("age", "blocks"), [(_STALE, False), (_FRESH, True)], ids=["stale", "fresh"])
async def test_only_a_live_running_run_supersedes_a_new_run(
    factory, age: timedelta, blocks: bool  # noqa: ANN001
) -> None:
    node = await _agent(factory)
    await _old_run(factory, node, LLCRunStatus.RUNNING.value, age)
    new = await _queued_run(factory, node)
    if blocks:
        with pytest.raises(RunSuperseded):
            await mark_running(factory, new)
        expected = LLCRunStatus.SKIPPED.value
    else:
        assert await mark_running(factory, new) == 0
        expected = LLCRunStatus.RUNNING.value
    async with factory() as session:
        assert (await session.get(LLCHeartbeatRun, new)).status == expected


# -- MEDIUM 1 + 2: a wake that cannot start never fails the user's write ------------------


async def _assignee(factory, item_id: uuid.UUID) -> str:  # noqa: ANN001
    async with factory() as session:
        return (await session.get(LLCWorkItem, item_id)).assignee_agent_id


async def test_an_unconfigured_agent_does_not_fail_the_assignment(factory, dispatched, caplog) -> None:  # noqa: ANN001
    node = await _agent(factory)
    item_id = await _item(factory)
    refused = ValueError(f"Agent {node.agent_id!r} not found or not configured")
    with patch.object(LLCHeartbeatScheduler, "trigger_manual", side_effect=refused):
        async with factory() as session:
            await _update_assignee(session, item_id, node)
            await session.commit()
    assert str(await _assignee(factory, item_id)) == str(node.id)  # the write stands
    assert await _runs(factory, node.agent_id) == [] and dispatched == []
    assert "not found or not configured" in caplog.text


async def test_a_dispatch_that_raises_after_commit_does_not_fail_the_commit(
    factory, dispatched, caplog
) -> None:  # noqa: ANN001
    node = await _agent(factory)
    item_id = await _item(factory)
    with patch.object(LLCHeartbeatScheduler, "dispatch_run", side_effect=RuntimeError("no running event loop")):
        async with factory() as session:
            await _update_assignee(session, item_id, node)
            await session.commit()  # must return normally: the data is already durable
    assert str(await _assignee(factory, item_id)) == str(node.id)
    (run,) = await _runs(factory, node.agent_id)
    assert run.status == LLCRunStatus.QUEUED.value  # left for the stalled-run sweep (#16817)
    assert "dispatch of run" in caplog.text
