# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for GH#12210 — hired agent can't run (heartbeat/trigger).

Repro: ``POST /companies/{id}/agent-hires`` never sets ``heartbeat_enabled``
(``AgentHireRequest.heartbeat_enabled`` defaults False, see
``llc/api/agent_hires.py``), then ``POST /agents/{agent_id}/heartbeat/trigger``
raised ``ValueError: Agent '<id>' not found or not configured`` from
``HeartbeatScheduler._get_agent_config`` — it filtered on
``heartbeat_enabled = true`` unconditionally, so a freshly hired agent that
never opted into the periodic cron was invisible to a manual trigger.

The org node is seeded directly via the ``AgentOrgNode`` ORM model against an
in-memory SQLite DB (the shared LLC loop harness — see ``_e2e_harness.py`` and
``test_llc_e2e_loop.py``'s own documented direct-seed pattern; hitting the real
hire *HTTP* route here is not viable because its raw ``text()`` INSERT omits
``created_at``/``updated_at``, relying on a Postgres-only server default that
the SQLite harness intentionally strips for ORM-issued inserts). The seeded
row mirrors exactly what the hire endpoint persists by default:
``heartbeat_enabled=False``, ``adapter_type="claude_code"``, a resolved model
in ``adapter_config``. The test then calls the scheduler's real
``trigger_manual`` — the exact code path ``llc/api/agents.py``'s trigger
endpoint invokes — and asserts it resolves the agent and queues a run instead
of raising "not found or not configured".
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import LLCRunStatus
from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

# Importing the harness registers the SQLite compile shims and loop models
# (including AgentOrgNode) on Base.metadata before create_all runs.
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole

_ORG = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )


async def _hire_agent(session_factory, *, heartbeat_enabled: bool = False) -> str:  # noqa: ANN001
    """Seed an ``AgentOrgNode`` matching what ``POST /agent-hires`` persists.

    ``heartbeat_enabled`` defaults False here to mirror
    ``AgentHireRequest.heartbeat_enabled``'s default (GH#12210 repro: the caller
    never sets it).
    """
    agent_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name="ABR CEO",
                org_role=OrgRole.MANAGER.value,
                company_id=_ORG,
                heartbeat_enabled=heartbeat_enabled,
                adapter_type="claude_code",
                adapter_config={"model": "claude-sonnet-4-6"},
                model="claude-sonnet-4-6",
            )
        )
        await session.commit()
    return agent_id


@pytest.mark.asyncio
async def test_hired_agent_can_be_manually_triggered(session_factory) -> None:  # noqa: ANN001
    """Hire (heartbeat_enabled defaults False) then trigger_manual must resolve it."""
    agent_id = await _hire_agent(session_factory)

    scheduler = HeartbeatScheduler()
    async with session_factory() as session:
        run, agent_cfg = await scheduler.trigger_manual(session, agent_id)
        await session.commit()

    assert agent_cfg["agent_id"] == agent_id
    assert not agent_cfg["heartbeat_enabled"]  # hire default, unchanged (GH#12210)
    assert run.status == LLCRunStatus.QUEUED.value


@pytest.mark.asyncio
async def test_unhired_agent_still_raises_not_found(session_factory) -> None:  # noqa: ANN001
    """No org node at all still fails fast — the fix must not open a blanket bypass."""
    scheduler = HeartbeatScheduler()
    async with session_factory() as session:
        with pytest.raises(ValueError, match="not found"):
            await scheduler.trigger_manual(session, "agent-does-not-exist")
