# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A run's checkouts are given back by the run, whichever way the run ends (#19601, #19600).

``LLCHeartbeatRun.work_item_id`` was never written, so run cancel and the liveness monitor released a
Redis fence inside ``if run.work_item_id`` -- never -- and left the DB checkout that the work queue
reads. The checkout is linked to its run by ``checkout_run_id`` alone, and one release serves the
stalled-run sweep, a cancel and the liveness monitor.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from sqlalchemy.dialects import postgresql

from llc.api import runs as runs_api
from llc.models.activity import ActorType
from llc.models.enums import WorkItemStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.services import run_checkouts
from llc.services.run_checkouts import ReleaseWhy, drop_released_fences, release_checkouts_for_run
from llc.services.work_item_queue import checkout_next
from llc.tests._run_checkout_world import Item, QueueSession, Recorder, RoutedSession, bound_values

_COMPANY = uuid.uuid4()


def _run(company: uuid.UUID = _COMPANY, status: str = "running") -> LLCHeartbeatRun:
    return LLCHeartbeatRun(
        id=uuid.uuid4(),
        company_id=company,
        agent_id="agent-1",
        invocation_source="schedule",
        status=status,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def fences(monkeypatch):  # noqa: ANN001, ANN201
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(run_checkouts, "get_async_redis_client", AsyncMock(return_value=redis))
    return redis


@pytest.mark.asyncio
async def test_release_clears_every_item_the_run_checked_out_and_no_other() -> None:
    run, other = _run(), _run()
    mine = [Item(_COMPANY, run.id), Item(_COMPANY, run.id)]
    theirs, unclaimed = Item(_COMPANY, other.id), Item(_COMPANY)
    session = RoutedSession([run], [*mine, theirs, unclaimed])
    log = Recorder()

    released = await release_checkouts_for_run(session, run, ReleaseWhy("cancelled", "run_cancel", log=log))

    assert {r.item.id for r in released} == {i.id for i in mine}
    for item in mine:
        assert (item.checkout_run_id, item.checkout_locked_at, item.version) == (None, None, 2)
    assert theirs.checkout_run_id == str(other.id) and theirs.version == 1
    assert unclaimed.version == 1
    assert len(log.entries) == 2


@pytest.mark.asyncio
async def test_each_release_records_the_true_reason_and_actor() -> None:
    run = _run()
    item = Item(_COMPANY, run.id)
    user = str(uuid.uuid4())
    log = Recorder()
    why = ReleaseWhy("cancelled", "run_cancel", ActorType.USER, user, log)

    await release_checkouts_for_run(RoutedSession([run], [item]), run, why)

    [entry] = log.entries
    assert entry["metadata"] == {"reason": "cancelled", "heartbeat_run_id": str(run.id), "source": "run_cancel"}
    assert (entry["actor_type"], entry["actor_id"], entry["entity_id"]) == (ActorType.USER, user, str(item.id))
    assert entry["before"] == {"checkout_run_id": str(run.id), "status": "in_progress"}
    assert entry["after"] == {"checkout_run_id": None, "status": "ready"}


@pytest.mark.asyncio
async def test_a_second_release_finds_nothing() -> None:
    run = _run()
    session = RoutedSession([run], [Item(_COMPANY, run.id)])
    why = ReleaseWhy("cancelled", "run_cancel", log=Recorder())
    assert len(await release_checkouts_for_run(session, run, why)) == 1
    assert await release_checkouts_for_run(session, run, why) == []


def test_the_lookup_is_bounded_by_the_runs_company_and_row_locked() -> None:
    statement = run_checkouts.checkouts_held_by("run-1", _COMPANY)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "checkout_run_id" in sql and "company_id" in sql and "FOR UPDATE" in sql
    assert _COMPANY in bound_values(statement)


@pytest.mark.asyncio
async def test_only_the_fence_of_the_released_generation_is_dropped(fences) -> None:  # noqa: ANN001
    run = _run()
    item, newer = Item(_COMPANY, run.id), Item(_COMPANY, run.id)
    released = await release_checkouts_for_run(
        RoutedSession([run], [item, newer]), run, ReleaseWhy("cancelled", "run_cancel", log=Recorder())
    )
    held_fence = f"{item.assignee_agent_id}#{run.id}"
    await fences.set(released[0].fence_key, held_fence)
    # The same agent checked the other item out again in a later run: that generation is not ours to drop.
    await fences.set(released[1].fence_key, f"{newer.assignee_agent_id}#{uuid.uuid4()}")

    await drop_released_fences(released)

    assert await fences.get(released[0].fence_key) is None
    assert await fences.get(released[1].fence_key) is not None


def _user_ctx(run: LLCHeartbeatRun) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = run.company_id
    return ctx


@pytest.mark.asyncio
async def test_cancel_releases_every_checkout_and_fence_with_the_cancel_reason(
    fences, monkeypatch  # noqa: ANN001
) -> None:
    run, other = _run(), _run()
    mine = [Item(_COMPANY, run.id), Item(_COMPANY, run.id)]
    theirs = Item(_COMPANY, other.id)
    session = RoutedSession([run], [*mine, theirs])
    log = Recorder()
    monkeypatch.setattr(run_checkouts, "_activity_log", log)
    for item in (*mine, theirs):
        await fences.set(f"llc:checkout:{item.id}", item.fence)
    user = str(uuid.uuid4())

    with patch.object(runs_api, "get_adapter_for_agent", AsyncMock(return_value=None)):
        result = await runs_api.cancel_run(run.agent_id, str(run.id), session, {"id": user}, _user_ctx(run))

    assert result["status"] == "cancelled" and session.commits == 1
    for item in mine:
        assert item.checkout_run_id is None and item.checkout_locked_at is None
        assert item.status == WorkItemStatus.READY, "a cancelled run's unfinished item is claimable again"
        assert await fences.get(f"llc:checkout:{item.id}") is None, "the fence must not outlive the checkout"
    assert theirs.checkout_run_id == str(other.id)
    assert await fences.get(f"llc:checkout:{theirs.id}") == theirs.fence
    assert sorted(e["entity_id"] for e in log.entries) == sorted(str(i.id) for i in mine)
    assert {e["metadata"]["reason"] for e in log.entries} == {"cancelled"}
    assert {(e["actor_type"], e["actor_id"]) for e in log.entries} == {(ActorType.USER, user)}


@pytest.mark.asyncio
async def test_a_cancel_by_a_credential_that_is_not_a_person_is_the_systems_act(
    fences, monkeypatch  # noqa: ANN001
) -> None:
    run = _run()
    log = Recorder()
    monkeypatch.setattr(run_checkouts, "_activity_log", log)
    session = RoutedSession([run], [Item(_COMPANY, run.id)])

    with patch.object(runs_api, "get_adapter_for_agent", AsyncMock(return_value=None)):
        await runs_api.cancel_run(run.agent_id, str(run.id), session, {"username": "svc"}, _user_ctx(run))

    [entry] = log.entries
    assert (entry["actor_type"], entry["actor_id"]) == (ActorType.SYSTEM, None)


@pytest.mark.asyncio
async def test_an_unfinished_item_goes_back_to_ready_with_its_assignee_and_is_offered_again() -> None:
    run = _run()
    item = Item(_COMPANY, run.id)
    agent = item.assignee_agent_id
    await release_checkouts_for_run(
        RoutedSession([run], [item]), run, ReleaseWhy("cancelled", "run_cancel", log=Recorder())
    )
    assert (item.status, item.assignee_agent_id) == (WorkItemStatus.READY, agent)

    service = MagicMock(checkout=AsyncMock(return_value=item))
    offered = await checkout_next(QueueSession([item]), service, str(agent), str(_COMPANY))

    assert offered is item
    assert service.checkout.await_args.kwargs["work_item_id"] == str(item.id)


@pytest.mark.asyncio
async def test_an_item_still_in_progress_is_not_offered_before_the_release() -> None:
    item = Item(_COMPANY, uuid.uuid4())
    service = MagicMock(checkout=AsyncMock())
    assert await checkout_next(QueueSession([item]), service, str(item.assignee_agent_id), str(_COMPANY)) is None
    service.checkout.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["in_review", "blocked", "done", "cancelled"])
async def test_an_item_that_moved_on_keeps_its_status_and_only_loses_the_stale_checkout(status: str) -> None:
    run = _run()
    item = Item(_COMPANY, run.id)
    item.status = status
    log = Recorder()

    released = await release_checkouts_for_run(
        RoutedSession([run], [item]), run, ReleaseWhy("stalled", "sweep", log=log)
    )

    assert item.status == status and item.checkout_run_id is None and not released[0].moved
    [entry] = log.entries
    assert entry["before"] == {"checkout_run_id": str(run.id)} and entry["after"] == {"checkout_run_id": None}


@pytest.mark.asyncio
async def test_a_caller_may_park_unfinished_items_somewhere_else_but_only_those() -> None:
    run = _run()
    working, reviewed = Item(_COMPANY, run.id), Item(_COMPANY, run.id)
    reviewed.status = "in_review"
    why = ReleaseWhy("liveness_timeout", "liveness", log=Recorder(), then=WorkItemStatus.BLOCKED)

    released = await release_checkouts_for_run(RoutedSession([run], [working, reviewed]), run, why)

    assert (working.status, reviewed.status) == (WorkItemStatus.BLOCKED, "in_review")
    assert [r.moved for r in released] == [True, False]


@pytest.mark.asyncio
async def test_the_live_run_is_the_running_one_before_a_newer_queued_one_and_is_locked_shared() -> None:
    """Compiled, because sqlite cannot prove ordering across the status column or row locking."""

    class _Capture:
        statement = None

        async def execute(self, statement):  # noqa: ANN001, ANN202
            self.statement = statement
            return MagicMock(scalar_one_or_none=lambda: None)

    session = _Capture()
    await run_checkouts.live_run_id(session, "agent-1", str(_COMPANY))
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    order = sql.split("ORDER BY")[1]
    assert order.index("CASE") < order.index("created_at DESC"), "a RUNNING run must outrank a newer QUEUED one"
    assert "FOR SHARE" in sql
    assert "running" in bound_values(session.statement)
