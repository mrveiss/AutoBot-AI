# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two concurrent RUNNING claims for one agent: exactly one wins (#19582 review).

``run_status.claim_running`` reads the agent's ``agent_org_nodes`` row ``FOR
UPDATE`` before its conditional UPDATE. Without the lock, two claims for different
runs of one agent each evaluate ``NOT EXISTS (other RUNNING run)`` against a
snapshot that cannot see the other's uncommitted RUNNING, and under READ COMMITTED
both win -- the agent runs twice at once.

Real Postgres only -- SQLite has no row locks, so this lives on the
migration-gate path with its siblings (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

#: Long enough that a claim which is NOT waiting on the lock has finished.
_BLOCKED_PROBE_SECONDS = 1.0


@pytest.fixture()
async def maker(fresh_db_url):  # noqa: ANN001,ANN201
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(maker) -> tuple[str, uuid.UUID, uuid.UUID]:  # noqa: ANN001
    """One agent and two QUEUED runs of it: a tick's and an event's."""
    from llc.models.enums import LLCRunStatus
    from llc.models.heartbeat_run import LLCHeartbeatRun
    from models.agent_org import AgentOrgNode

    company, slug = uuid.uuid4(), f"bot-{uuid.uuid4().hex[:8]}"
    runs = [uuid.uuid4(), uuid.uuid4()]
    async with maker() as session:
        session.add(AgentOrgNode(id=uuid.uuid4(), agent_id=slug, name="Bot", company_id=company))
        for run_id, source in zip(runs, ("scheduler", "work_item_assigned")):
            session.add(
                LLCHeartbeatRun(
                    id=run_id,
                    company_id=company,
                    agent_id=slug,
                    invocation_source=source,
                    status=LLCRunStatus.QUEUED.value,
                )
            )
        await session.commit()
    return slug, runs[0], runs[1]


async def test_a_second_claim_waits_for_the_first_and_then_loses(maker):  # noqa: ANN001
    from llc.models.heartbeat_run import LLCHeartbeatRun
    from llc.scheduler.run_status import claim_running

    slug, first, second = await _seed(maker)
    async with maker() as a, maker() as b:
        assert await claim_running(a, first, slug)
        late = asyncio.create_task(claim_running(b, second, slug))
        done, _ = await asyncio.wait({late}, timeout=_BLOCKED_PROBE_SECONDS)
        assert not done, "the second claim did not wait for the first one's agent row lock"
        await a.commit()
        assert await late is False, "both claims won: the agent would run twice at once"
        await b.commit()
    async with maker() as session:
        rows = (await session.execute(sa.select(LLCHeartbeatRun.id, LLCHeartbeatRun.status))).all()
    assert {row.id: row.status for row in rows} == {first: "running", second: "queued"}
