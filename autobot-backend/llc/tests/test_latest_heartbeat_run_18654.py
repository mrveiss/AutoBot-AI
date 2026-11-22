# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One heartbeat run per agent, and it is the one that says what the agent is doing (#18654).

`agent_org_nodes_with_latest_heartbeat` feeds both the agents list and the presence
feed. It used to join `max(created_at)` back without a tie-break, so a tie listed
an agent twice, and an older run still RUNNING behind a newer one read as idle.
Owner ruling (2026-10-17): any running run wins; otherwise the newest; ties by id.
Run against the real query on SQLite through the loop harness.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import HeartbeatInvocationSource, LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.services.agent_presence_queries import agent_org_nodes_with_latest_heartbeat
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole

T0 = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def sessions():  # noqa: ANN201
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _agent(sessions, company: uuid.UUID, slug: str) -> None:  # noqa: ANN001
    async with sessions() as session:
        session.add(
            AgentOrgNode(id=uuid.uuid4(), company_id=company, agent_id=slug, name=slug, org_role=OrgRole.WORKER)
        )
        await session.commit()


async def _run(
    sessions, company: uuid.UUID, slug: str, status: LLCRunStatus, at: datetime
) -> uuid.UUID:  # noqa: ANN001
    run_id = uuid.uuid4()
    async with sessions() as session:
        session.add(
            LLCHeartbeatRun(
                id=run_id,
                company_id=company,
                agent_id=slug,
                invocation_source=HeartbeatInvocationSource.SCHEDULER.value,
                status=status.value,
                created_at=at,
            )
        )
        await session.commit()
    return run_id


async def _rows(sessions, company: uuid.UUID) -> list:  # noqa: ANN001
    # A uuid.UUID, not str: SQLite's non-native UUID type binds only uuid.UUID,
    # while PostgreSQL's native one also takes the str the production callers pass.
    query = agent_org_nodes_with_latest_heartbeat(company)  # type: ignore[arg-type]
    async with sessions() as session:
        return (await session.execute(query)).all()


@pytest.mark.asyncio
async def test_a_created_at_tie_still_lists_the_agent_once_choosing_the_higher_id(sessions) -> None:  # noqa: ANN001
    company = uuid.uuid4()
    await _agent(sessions, company, "writer")
    ids = [await _run(sessions, company, "writer", LLCRunStatus.COMPLETED, T0) for _ in range(2)]

    rows = await _rows(sessions, company)

    assert len(rows) == 1
    assert rows[0][1].id == max(ids)


@pytest.mark.asyncio
async def test_an_older_running_run_wins_over_a_newer_finished_one(sessions) -> None:  # noqa: ANN001
    company = uuid.uuid4()
    await _agent(sessions, company, "writer")
    running = await _run(sessions, company, "writer", LLCRunStatus.RUNNING, T0)
    await _run(sessions, company, "writer", LLCRunStatus.COMPLETED, T0 + timedelta(minutes=5))

    [(node, run)] = await _rows(sessions, company)

    assert (run.id, run.status) == (running, LLCRunStatus.RUNNING.value)


@pytest.mark.asyncio
async def test_with_nothing_running_the_newest_run_is_shown(sessions) -> None:  # noqa: ANN001
    company = uuid.uuid4()
    await _agent(sessions, company, "writer")
    await _run(sessions, company, "writer", LLCRunStatus.COMPLETED, T0)
    newest = await _run(sessions, company, "writer", LLCRunStatus.QUEUED, T0 + timedelta(minutes=5))

    [(_node, run)] = await _rows(sessions, company)

    assert run.id == newest


@pytest.mark.asyncio
async def test_an_agent_with_no_runs_is_kept_and_another_companys_run_is_never_chosen(sessions) -> None:  # noqa: ANN001
    # Org-node slugs are unique, but a run row carries its own company and slug with no
    # such constraint -- one filed under another company must not attach to this agent.
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _agent(sessions, mine, "writer")
    await _run(sessions, theirs, "writer", LLCRunStatus.RUNNING, T0)

    [(node, run)] = await _rows(sessions, mine)

    assert node.company_id == mine and run is None
