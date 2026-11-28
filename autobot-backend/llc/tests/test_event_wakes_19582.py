# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19582 — events wake an agent through ONE dispatcher, independent of the heartbeat.

Each test drives a real write point (``WorkItemService``, ``ApprovalService``) on an
in-memory SQLite schema, commits, and reads back the run row and the dispatch the
commit fired. ``dispatch_run`` is replaced by a recorder so no adapter actually runs.

AC map (issue #19582):
  1. each of the 4 events wakes a heartbeat-OFF active agent -> ``test_<event>_wakes_*``
  2. dormant/inactive/terminated is not woken                -> ``test_an_unwakeable_status_*``
  3. a NULL-adapter agent is woken                            -> ``test_a_null_adapter_agent_*``
  4. a heartbeat-off agent gets no periodic tick              -> ``test_a_heartbeat_off_agent_gets_no_tick``
  5. one dispatcher                                           -> ``test_event_wake_guard_19582.py``
  6. event + tick do not double-run                           -> ``test_an_event_*_tick_*``
"""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable, Dict, List
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import ApprovalStatus, HeartbeatInvocationSource, LLCRunStatus, WorkItemType
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.scheduler.heartbeat_scheduler import LLCHeartbeatScheduler, _dispatch_adapter
from llc.scheduler.run_status import RunSuperseded, mark_running
from llc.services.approval import ApprovalService
from llc.services.work_item_service import WorkItemService

# Importing the harness registers the SQLite compile shims before any model code.
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole
from models.approval import Approval

_COMPANY = uuid.uuid4()
_OTHER_COMPANY = uuid.uuid4()
_USER = uuid.uuid4()
_SRC = HeartbeatInvocationSource


@pytest_asyncio.fixture
async def factory():  # noqa: ANN201
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(eng)
    approvals = Approval.__table__
    harness._scrub_pg_server_defaults(approvals)
    harness._clientside_timestamps(approvals)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: approvals.create(c, checkfirst=True))
    yield async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)  # canonical: ignore py-adhoc-db-engine
    await eng.dispose()


@pytest.fixture
def dispatched():  # noqa: ANN201
    """Every ``dispatch_run`` call a commit fires, as ``(agent_cfg, run_id, context)``."""
    calls: List[tuple] = []
    # The dispatch gate refuses when it cannot read pause flags (#19240), so it gets a Redis with none set.
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    with (
        patch.object(LLCHeartbeatScheduler, "dispatch_run", lambda self, a, r, c=None: calls.append((a, r, c))),
        patch("llc.scheduler.dispatch_gate.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        yield calls


async def _agent(factory, *, status: str = "available", company=_COMPANY, adapter=None) -> AgentOrgNode:  # noqa: ANN001
    """A heartbeat-OFF agent (the hire default) with a slug distinct from its PK."""
    node = AgentOrgNode(
        id=uuid.uuid4(),
        name="Bot",
        org_role=OrgRole.WORKER.value,
        company_id=company,
        adapter_type=adapter,
        heartbeat_enabled=False,
        status=status,
    )
    node.agent_id = f"bot-{node.id.hex[:8]}"
    async with factory() as session:
        session.add(node)
        await session.commit()
    return node


async def _item(factory, assignee=None, description=None) -> uuid.UUID:  # noqa: ANN001
    async with factory() as session:
        item = await WorkItemService().create(
            session,
            str(_COMPANY),
            WorkItemType.TASK,
            "Task",
            description=description,
            assignee_agent_id=assignee,
            project_id=await harness.seed_project(session, _COMPANY),
        )
        await session.commit()
        return item.id


async def _runs(factory, slug: str) -> List[LLCHeartbeatRun]:  # noqa: ANN001
    async with factory() as session:
        result = await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.agent_id == slug))
        return list(result.scalars())


# -- the four events, each as a callable over (factory, agent) -----------------------------


async def _comment(factory, node: AgentOrgNode) -> None:  # noqa: ANN001
    item_id = await _item(factory, assignee=str(node.id))
    for run in await _runs(factory, node.agent_id):  # the assignment woke it; finish that run first
        await _set_status(factory, run.id, LLCRunStatus.COMPLETED.value)
    async with factory() as session:
        await WorkItemService().add_comment(session, str(item_id), str(_COMPANY), "ping", author_user_id=str(_USER))
        await session.commit()


async def _assign(factory, node: AgentOrgNode) -> None:  # noqa: ANN001
    item_id = await _item(factory)
    async with factory() as session:
        await WorkItemService().update(session, str(item_id), assignee_agent_id=node.id)
        await session.commit()


async def _mention(factory, node: AgentOrgNode) -> None:  # noqa: ANN001
    item_id = await _item(factory)
    async with factory() as session:
        body = f"@{node.agent_id} can you look at this?"
        await WorkItemService().add_comment(session, str(item_id), str(_COMPANY), body, author_user_id=str(_USER))
        await session.commit()


async def _approval(factory, node: AgentOrgNode) -> None:  # noqa: ANN001
    async with factory() as session:
        approval = await ApprovalService().request_approval(
            session, company_id=_COMPANY, gate_type=_approval_type(), requested_by=node.id, payload={}
        )
        await session.commit()
    async with factory() as session:
        await ApprovalService().decide(
            session, approval_id=approval.id, decision=ApprovalStatus.APPROVED, decided_by=_USER
        )
        await session.commit()


def _approval_type() -> Any:
    from llc.models.enums import ApprovalType

    return next(iter(ApprovalType))


_EVENTS: Dict[str, tuple] = {
    "comment": (_comment, _SRC.WORK_ITEM_COMMENTED),
    "assignment": (_assign, _SRC.WORK_ITEM_ASSIGNED),
    "mention": (_mention, _SRC.AGENT_MENTIONED),
    "approval": (_approval, _SRC.APPROVAL_DECIDED),
}


async def _set_status(factory, run_id: uuid.UUID, status: str) -> None:  # noqa: ANN001
    async with factory() as session:
        run = await session.get(LLCHeartbeatRun, run_id)
        run.status = status
        await session.commit()


# -- AC 1: each event wakes a heartbeat-OFF agent ------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("event", sorted(_EVENTS))
async def test_each_event_wakes_a_heartbeat_off_agent(factory, dispatched, event: str) -> None:  # noqa: ANN001
    fire, source = _EVENTS[event]
    node = await _agent(factory)
    await fire(factory, node)
    runs = [r for r in await _runs(factory, node.agent_id) if r.invocation_source == source.value]
    assert len(runs) == 1, f"{event} must start exactly one run"
    assert runs[0].context_snapshot["wake_reason"] == source.value  # the run shows why it started
    assert runs[0].company_id == _COMPANY
    assert runs[0].id in [run_id for _, run_id, _ in dispatched]  # dispatched on commit


# -- AC 2: dormant, inactive or terminated is never woken ----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["paused", "inactive", "terminated"])
@pytest.mark.parametrize("event", sorted(_EVENTS))
async def test_an_unwakeable_status_is_not_woken(factory, dispatched, event: str, status: str) -> None:  # noqa: ANN001
    fire, _ = _EVENTS[event]
    node = await _agent(factory, status=status)
    await fire(factory, node)
    assert await _runs(factory, node.agent_id) == []
    assert dispatched == []


# -- AC 3: a NULL-adapter (in-process) agent is woken and runs on the heartbeat's runner ---


@pytest.mark.asyncio
async def test_a_null_adapter_agent_is_woken_and_falls_back_in_process(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory, adapter=None)
    await _assign(factory, node)
    (agent_cfg, _, context), *_ = dispatched
    assert agent_cfg["adapter_type"] is None
    assert agent_cfg["org_role"] == OrgRole.WORKER.value  # #16950: the dispatch can bound the run
    with patch("llc.scheduler.heartbeat_scheduler._dispatch_autobot_agent") as in_process:
        await _dispatch_adapter(agent_cfg, context)
    in_process.assert_awaited_once()


# -- AC 4: heartbeat_enabled still gates the periodic tick ---------------------------------


@pytest.mark.asyncio
async def test_a_heartbeat_off_agent_gets_no_tick(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    await _assign(factory, node)  # an event wake does not opt it into the schedule
    sched = LLCHeartbeatScheduler()
    async with factory() as session:
        assert await sched._get_agent_config(session, node.agent_id) is None  # the tick's own lookup
    with patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=factory):
        assert node.agent_id not in [a["agent_id"] for a in await sched._load_enabled_agents()]


# -- AC 6: an event and a tick never run the agent twice -----------------------------------


@pytest.mark.asyncio
async def test_an_event_during_a_tick_run_starts_no_second_run(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    tick = await _tick_run(factory, node, LLCRunStatus.RUNNING.value)
    await _assign(factory, node)
    assert [r.id for r in await _runs(factory, node.agent_id)] == [tick]
    assert dispatched == []


@pytest.mark.asyncio
async def test_a_tick_during_an_event_run_is_superseded(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    await _assign(factory, node)
    (_, event_run, _), *_ = dispatched
    assert await mark_running(factory, event_run) == 0  # the event run takes RUNNING
    tick = await _tick_run(factory, node, LLCRunStatus.QUEUED.value)
    with pytest.raises(RunSuperseded):
        await mark_running(factory, tick)
    async with factory() as session:
        assert (await session.get(LLCHeartbeatRun, tick)).status == LLCRunStatus.SKIPPED.value


@pytest.mark.asyncio
async def test_two_events_in_one_write_start_one_run(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    await _item(factory, assignee=str(node.id), description=f"cc @{node.agent_id}")  # assigned AND mentioned
    assert len(await _runs(factory, node.agent_id)) == 1
    assert len(dispatched) == 1


async def _tick_run(factory, node: AgentOrgNode, status: str) -> uuid.UUID:  # noqa: ANN001
    async with factory() as session:
        run = LLCHeartbeatRun(
            id=uuid.uuid4(), company_id=_COMPANY, agent_id=node.agent_id, invocation_source="scheduler", status=status
        )
        session.add(run)
        await session.commit()
        return run.id


# -- the dispatcher's own rules ------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_mention_never_crosses_companies(factory, dispatched) -> None:  # noqa: ANN001
    outsider = await _agent(factory, company=_OTHER_COMPANY)
    await _mention(factory, outsider)
    assert await _runs(factory, outsider.agent_id) == []


@pytest.mark.asyncio
async def test_an_agents_own_comment_does_not_wake_it(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    item_id = await _item(factory)
    async with factory() as session:
        await WorkItemService().update(session, str(item_id), assignee_agent_id=node.id)
        await session.commit()
    await _set_status(factory, (await _runs(factory, node.agent_id))[0].id, LLCRunStatus.COMPLETED.value)
    async with factory() as session:
        await WorkItemService().add_comment(session, str(item_id), str(_COMPANY), "done", author_agent_id=str(node.id))
        await session.commit()
    assert [r.invocation_source for r in await _runs(factory, node.agent_id)] == [_SRC.WORK_ITEM_ASSIGNED.value]


@pytest.mark.asyncio
@pytest.mark.parametrize("savepoint", [False, True])
async def test_a_rolled_back_wake_is_never_dispatched(factory, dispatched, savepoint: bool) -> None:  # noqa: ANN001
    node = await _agent(factory)
    item_id = await _item(factory)
    async with factory() as session:
        await _rollback_after(session, savepoint, lambda: _update_assignee(session, item_id, node))
        await session.commit()
    assert dispatched == []
    assert await _runs(factory, node.agent_id) == []


async def _update_assignee(session: AsyncSession, item_id: uuid.UUID, node: AgentOrgNode) -> None:
    await WorkItemService().update(session, str(item_id), assignee_agent_id=node.id)


async def _rollback_after(session: AsyncSession, savepoint: bool, write: Callable[[], Awaitable[None]]) -> None:
    if not savepoint:
        await write()
        await session.rollback()
        return
    nested = await session.begin_nested()
    await write()
    await nested.rollback()


@pytest.mark.asyncio
async def test_a_non_event_source_is_refused(factory) -> None:  # noqa: ANN001
    from llc.scheduler.event_wake import wake_agent

    async with factory() as session:
        with pytest.raises(ValueError):
            await wake_agent(session, company_id=_COMPANY, agent_ref="x", reason=_SRC.SCHEDULER)
