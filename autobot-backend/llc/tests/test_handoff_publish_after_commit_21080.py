# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Handoff notifications go out only once the caller's transaction commits (#21080).

A subscriber must never see a handoff that rolls back. Real SQLite sessions: the commit and rollback hooks
are SQLAlchemy events, which a fake session does not fire.
"""

import asyncio
import json
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.services import commit_publish
from llc.services.handoff import HandoffService
from llc.tests import _e2e_harness as harness
from testkit.fake_async_session import FakeAsyncSession

COMPANY, WORK_ITEM, AGENT, USER = (str(uuid.uuid4()) for _ in range(4))
BRIEF = {"title": "t", "identifier": "WI-1"}


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(engine)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def redis():  # noqa: ANN201
    client = AsyncMock()
    with patch("llc.services.commit_publish.get_async_redis_client", AsyncMock(return_value=client)):
        yield client


async def _drain() -> None:
    await asyncio.sleep(0)
    if commit_publish._publish_tasks:
        await asyncio.gather(*commit_publish._publish_tasks)


async def _both(session) -> None:  # noqa: ANN001
    service = HandoffService()
    await session.execute(text("SELECT 1"))  # a handoff has read the item, so its transaction is open
    await service._publish_h2a_notification(session, COMPANY, AGENT, WORK_ITEM)
    await service._publish_a2h_notification(session, COMPANY, WORK_ITEM, USER, BRIEF)


async def test_nothing_is_published_before_the_commit(session, redis):  # noqa: ANN001
    await _both(session)
    await _drain()
    redis.publish.assert_not_called()


async def test_a_rollback_publishes_nothing(session, redis):  # noqa: ANN001
    await _both(session)
    await session.rollback()
    await session.commit()
    await _drain()
    redis.publish.assert_not_called()


async def test_a_commit_publishes_each_notification_exactly_once(session, redis):  # noqa: ANN001
    await _both(session)
    await session.commit()
    await session.commit()
    await _drain()
    events = [json.loads(c.args[1])["event_type"] for c in redis.publish.call_args_list]
    assert sorted(events) == ["work_item.handoff", "work_item.handoff_ready"]
    assert {c.args[0] for c in redis.publish.call_args_list} == {f"llc:notifications:{COMPANY}"}


async def test_a_rolled_back_savepoint_drops_only_its_own_notification(session, redis):  # noqa: ANN001
    service = HandoffService()
    await session.execute(text("SELECT 1"))
    await service._publish_h2a_notification(session, COMPANY, AGENT, WORK_ITEM)
    nested = await session.begin_nested()
    await service._publish_a2h_notification(session, COMPANY, WORK_ITEM, USER, BRIEF)
    await nested.rollback()
    await session.commit()
    await _drain()
    redis.publish.assert_called_once()
    assert json.loads(redis.publish.call_args.args[1])["event_type"] == "work_item.handoff_ready"


async def test_a_session_without_a_commit_to_follow_publishes_at_once(redis):  # noqa: ANN001
    await HandoffService()._publish_h2a_notification(FakeAsyncSession(), COMPANY, AGENT, WORK_ITEM)
    redis.publish.assert_called_once()
