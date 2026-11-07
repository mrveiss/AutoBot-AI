# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The checkout fence is released after the transition commits, and a person's claim is not taken over (#20930)."""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from llc.models.enums import WorkItemStatus
from llc.services import work_item_own_task as own_task
from llc.services.work_item_service import CheckoutConflict, WorkItemService
from testkit.fake_async_session import FakeAsyncSession

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_AGENT = uuid.uuid4()


class _TxSession(FakeAsyncSession):
    """A fake whose commit and rollback also drive a real SQLAlchemy session, so its hooks fire as in production."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.sync_session = Session()
        self.sync_session.begin()  # the SELECT ... FOR UPDATE that precedes a transition has opened it

    async def commit(self) -> None:
        await super().commit()
        self.sync_session.commit()

    async def rollback(self) -> None:
        await super().rollback()
        self.sync_session.rollback()


def _item(*, user=None, agent=None, run=None) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(), company_id=uuid.uuid4(), status=WorkItemStatus.IN_PROGRESS, assignee_user_id=user,
        assignee_agent_id=agent, checkout_run_id=run, checkout_locked_at=_NOW, completed_at=None, cancelled_at=None,
        started_at=_NOW, version=1,
    )  # fmt: skip


async def _settle() -> None:
    await asyncio.gather(*own_task._release_tasks)


def _stamp(session: _TxSession, item: MagicMock) -> None:
    own_task.stamp_and_release(session, item, WorkItemStatus.DONE, _NOW)


@pytest.fixture
def release():
    with (
        patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=MagicMock())),
        patch.object(own_task, "delete_if_value", new=AsyncMock()) as deleted,
    ):
        yield deleted


async def test_the_fence_stays_until_the_commit(release) -> None:
    session, item = _TxSession(), _item(agent=_AGENT, run="r")
    _stamp(session, item)
    await _settle()
    release.assert_not_awaited()
    await session.commit()
    await _settle()
    release.assert_awaited_once()
    assert release.await_args.args[1:] == (f"llc:checkout:{item.id}", f"{_AGENT}#r")


async def test_a_rollback_keeps_the_fence(release) -> None:
    session = _TxSession()
    _stamp(session, _item(agent=_AGENT, run="r"))
    await session.rollback()
    await session.commit()
    await _settle()
    release.assert_not_awaited()


async def test_a_savepoint_rollback_drops_only_its_own_release(release) -> None:
    session, kept, undone = _TxSession(), _item(agent=_AGENT, run="r"), _item(agent=_AGENT, run="r")
    _stamp(session, kept)
    nested = session.sync_session.begin_nested()
    _stamp(session, undone)
    nested.rollback()
    await session.commit()
    await _settle()
    release.assert_awaited_once()
    assert release.await_args.args[1] == f"llc:checkout:{kept.id}"


async def test_a_redis_failure_after_the_commit_is_logged_and_never_fails_the_transition(release, caplog) -> None:
    release.side_effect = ConnectionError("redis down")
    session = _TxSession()
    _stamp(session, _item(agent=_AGENT, run="r"))
    await session.commit()  # does not raise
    await _settle()
    assert "expires on its TTL" in caplog.text


async def test_checkout_refuses_a_live_human_claim_and_keeps_the_claim() -> None:
    person = uuid.uuid4()
    item = _item(user=person)
    redis = MagicMock(set=AsyncMock(return_value=True), eval=AsyncMock())
    with patch("llc.services.work_item_service.get_async_redis_client", new=AsyncMock(return_value=redis)):
        with pytest.raises(CheckoutConflict, match=f"user {person}"):
            await WorkItemService(activity_log=MagicMock()).checkout(
                FakeAsyncSession(results=[[item]]), str(item.id), str(_AGENT)
            )
    assert item.assignee_user_id == person
    redis.eval.assert_awaited_once()  # the fence this call took


async def test_a_refused_checkout_leaves_a_fence_it_did_not_take() -> None:
    item = _item(agent=uuid.uuid4(), run="r")
    redis = MagicMock(set=AsyncMock(return_value=False), get=AsyncMock(return_value=str(_AGENT)), delete=AsyncMock())
    with patch("llc.services.work_item_service.get_async_redis_client", new=AsyncMock(return_value=redis)):
        with pytest.raises(CheckoutConflict):
            await WorkItemService(activity_log=MagicMock()).checkout(
                FakeAsyncSession(results=[[item]]), str(item.id), str(_AGENT)
            )
    redis.delete.assert_not_awaited()


async def test_a_deferred_release_does_not_drop_the_fence_of_a_later_checkout() -> None:
    """The same agent checks out again before an earlier transition's release runs: only its own generation goes."""
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    session, item = _TxSession(), _item(agent=_AGENT, run="gen-1")
    key = f"llc:checkout:{item.id}"
    await redis.set(key, own_task.checkout_fence_value(str(_AGENT), "gen-1"))
    _stamp(session, item)  # queues the release of generation 1
    await redis.set(key, own_task.checkout_fence_value(str(_AGENT), "gen-2"))  # re-checkout
    with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await session.commit()
        await _settle()
    assert await redis.get(key) == f"{_AGENT}#gen-2"
