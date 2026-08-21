# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Totalling the operation, and refusing to overstate what is known (GH#14599).

The rule under test is the arithmetic form of one this area has already broken
three times (#14064, #13617, #14556): silence must not read as zero. A step
nobody measured is excluded from the sum and counted in ``not_costable`` — it
is never folded in as costing nothing, which would make a partial total
indistinguishable from a complete one.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.role_rate import LLCRoleRate
from llc.models.role_tool import LLCRoleTool
from llc.models.role_workflow import LLCRoleWorkflow
from llc.services.step_rollup import StepRollupService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Only the tables this test touches — the pattern test_role_workflows.py sets.

    Not ``harness.create_loop_schema``: that builds an explicit list of *loop*
    models, and none of these are in it.
    """
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [
        Role.__table__,
        LLCRoleWorkflow.__table__,
        LLCRoleRate.__table__,
        LLCRoleTool.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed(session: AsyncSession, company_id: uuid.UUID) -> uuid.UUID:
    """One role, a rate, two workflows — one measured, one not — and a tool."""
    role_id = uuid.uuid4()
    session.add(Role(id=role_id, org_id=company_id, name="Head of Sales"))
    session.add(
        LLCRoleRate(
            id=uuid.uuid4(),
            company_id=company_id,
            role_id=role_id,
            hourly_rate=Decimal("120"),
            currency="EUR",
        )
    )
    session.add(
        LLCRoleWorkflow(
            id=uuid.uuid4(),
            company_id=company_id,
            role_id=role_id,
            workflow_id="wf-measured",
            estimated_minutes=30,
            runs_per_month=10,
        )
    )
    session.add(
        LLCRoleWorkflow(
            id=uuid.uuid4(),
            company_id=company_id,
            role_id=role_id,
            workflow_id="wf-unmeasured",
            estimated_minutes=None,
            runs_per_month=None,
        )
    )
    session.add(LLCRoleTool(id=uuid.uuid4(), company_id=company_id, role_id=role_id, tool_name="crm"))
    await session.flush()
    return role_id


@pytest.mark.asyncio
async def test_the_total_excludes_what_nobody_measured(session: AsyncSession) -> None:
    company_id = uuid.uuid4()
    await _seed(session, company_id)

    result = await StepRollupService().rollup(session, company_id)
    role = result["by_role"][0]

    # 30 minutes at 120/hour, ten times a month.
    assert role.per_month == Decimal("600")
    assert role.costed == 1
    # The unmeasured step is counted, not summed as zero.
    assert role.not_costable == 1
    assert role.total_steps == 2


@pytest.mark.asyncio
async def test_a_partial_total_never_claims_to_be_complete(session: AsyncSession) -> None:
    """The assertion that makes the total safe to read."""
    company_id = uuid.uuid4()
    await _seed(session, company_id)

    role = (await StepRollupService().rollup(session, company_id))["by_role"][0]

    assert role.is_complete is False
    # And it is not merely "no error": a real figure IS reported alongside.
    assert role.per_month > 0


@pytest.mark.asyncio
async def test_a_tool_carries_the_cost_of_the_steps_its_role_runs(session: AsyncSession) -> None:
    company_id = uuid.uuid4()
    await _seed(session, company_id)

    result = await StepRollupService().rollup(session, company_id)
    tool = result["by_tool"][0]

    assert tool.label == "crm"
    assert tool.per_month == Decimal("600")
    assert tool.not_costable == 1


@pytest.mark.asyncio
async def test_another_company_contributes_nothing(session: AsyncSession) -> None:
    """Scope is pinned on both sides of the join, so neither predicate alone widens it."""
    mine = uuid.uuid4()
    theirs = uuid.uuid4()
    await _seed(session, mine)
    await _seed(session, theirs)

    result = await StepRollupService().rollup(session, mine)

    assert len(result["by_role"]) == 1
    assert result["by_role"][0].per_month == Decimal("600")
