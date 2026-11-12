# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent API claims work inside the agent's own run, or not at all (#19600).

``GET /work-items/next`` passed no run to the claim, so the checkout was stamped with a random id that
named no run row and nothing could ever release it by run. The run is now found server-side from the
agent's credential and a claim without one is refused.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.tests import _e2e_harness as harness
from llc.tests.test_agent_stub_routes_15905 import (
    _factory_yielding,
    _request,
    _seed_agent_node,
    _seed_item,
    _seed_run,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as opened:
        yield opened
    await eng.dispose()


async def _finish_run(session: AsyncSession, run_id: uuid.UUID) -> None:
    """End a seeded run the way the sweep or a report does: a terminal status and a finish time."""
    run = (await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.id == run_id))).scalar_one()
    run.status = LLCRunStatus.COMPLETED.value
    run.finished_at = datetime.now(tz=timezone.utc)
    await session.commit()


async def test_the_next_route_refuses_when_the_agent_has_no_live_run(session):  # noqa: ANN001
    """#19600: no run, no claim -- not a random id naming no run that nothing could ever release."""
    from unittest.mock import patch

    from fastapi import HTTPException

    from llc.api import agent_api

    company = str(uuid.uuid4())
    item = await _seed_item(session, company, title="unclaimed")
    await _seed_agent_node(session, company, "agent-idle")
    finished = await _seed_run(session, company, "agent-idle")
    await _finish_run(session, finished)
    await _seed_run(session, str(uuid.uuid4()), "agent-idle")  # same slug, another company: not this agent's run

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        with pytest.raises(HTTPException) as refused:
            await agent_api.get_next_work_item(_request("agent-idle", company))

    assert refused.value.status_code == 409
    await session.refresh(item)
    assert item.checkout_run_id is None and item.assignee_agent_id is None


async def test_two_items_claimed_in_one_run_are_both_released_by_that_run(session):  # noqa: ANN001
    """The run is the link: every item it claimed is found by it, and another run's claim is not."""
    from unittest.mock import AsyncMock, patch

    from llc.api import agent_api
    from llc.services import run_checkouts
    from llc.services.run_checkouts import ReleaseWhy, release_checkouts_for_run

    company = str(uuid.uuid4())
    first = await _seed_item(session, company, title="one", position=1)
    second = await _seed_item(session, company, title="two", position=2)
    await _seed_agent_node(session, company, "agent-two")
    run_id = await _seed_run(session, company, "agent-two")
    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        await agent_api.get_next_work_item(_request("agent-two", company))
        await agent_api.get_next_work_item(_request("agent-two", company))
    run = (await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.id == run_id))).scalar_one()

    with patch.object(run_checkouts, "_activity_log", AsyncMock()):
        released = await release_checkouts_for_run(session, run, ReleaseWhy("cancelled", "run_cancel"))
    await session.commit()

    assert {r.item.id for r in released} == {first.id, second.id}
    for item in (first, second):
        await session.refresh(item)
        assert item.checkout_run_id is None and item.checkout_locked_at is None
