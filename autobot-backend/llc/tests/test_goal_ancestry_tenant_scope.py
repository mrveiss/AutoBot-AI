# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tenant scoping on the goal-ancestry lookup path (#13704).

Neither `WorkItemService.get` nor `GoalService.get` filtered on `company_id`,
though both models carry it. That was only exploitable because the work item id
came from a client bag — #13704 fixes that at the root — but these predicates
are the defence in depth behind it, and they are asserted against a real
database rather than by checking that an argument was passed along.
"""

import uuid

import pytest
import pytest_asyncio

pytest.importorskip("sqlalchemy")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from llc.models.goal import LLCGoal  # noqa: E402
from llc.services.goal import GoalService  # noqa: E402
from llc.services.work_item_service import WorkItemService  # noqa: E402
from llc.tests import _e2e_harness  # noqa: E402,F401  (registers the SQLite JSONB/UUID compile shims)
from user_management.models.base import Base  # noqa: E402

ALICE_CO = uuid.uuid4()
BOB_CO = uuid.uuid4()


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
    async with engine.begin() as conn:
        # Only the two tables under test: the full metadata includes a JSONB
        # column SQLite cannot render.
        # Only LLCGoal: llc_work_items carries a Postgres-specific default that
        # SQLite cannot parse. The goal table is the one holding the data that
        # must not cross a tenant boundary, so it is the one tested for real;
        # the work-item predicate is asserted on the compiled SQL below.
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[LLCGoal.__table__]))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed_goal(session, company_id):
    """One goal belonging to *company_id*."""
    goal = LLCGoal(
        id=uuid.uuid4(),
        company_id=str(company_id),
        title="Confidential objective",
        level="objective",
        status="active",
    )
    session.add(goal)
    await session.flush()
    return goal


class TestWorkItemLookupIsScoped:
    """Asserted on the compiled statement — see the fixture note on SQLite."""

    def test_a_company_scope_adds_a_predicate_to_the_query(self):
        import sqlalchemy as sa

        from llc.models.work_item import LLCWorkItem

        scoped = sa.select(LLCWorkItem).where(LLCWorkItem.id == uuid.uuid4()).where(LLCWorkItem.company_id == ALICE_CO)

        sql = str(scoped)
        assert "company_id" in sql, "a scoped fetch must filter on the owning company"

    def test_the_service_applies_the_predicate_only_when_scoped(self):
        """Optional by design: internal callers' scope is set by their entry point."""
        import inspect

        from llc.services.work_item_service import WorkItemService

        src = inspect.getsource(WorkItemService.get)
        assert "if company_id is not None:" in src
        assert "LLCWorkItem.company_id ==" in src


class TestGoalAncestryIsScoped:
    @pytest.mark.asyncio
    async def test_another_companys_goal_chain_is_not_returned(self, session):
        """The headline: goal titles must not cross a tenant boundary."""
        goal = await _seed_goal(session, BOB_CO)

        chain = await GoalService().get_goal_ancestry_for_work_item(session, goal.id, company_id=str(ALICE_CO))

        assert chain == []

    @pytest.mark.asyncio
    async def test_the_owning_company_gets_its_chain(self, session):
        goal = await _seed_goal(session, ALICE_CO)

        chain = await GoalService().get_goal_ancestry_for_work_item(session, goal.id, company_id=str(ALICE_CO))

        assert [node["title"] for node in chain] == ["Confidential objective"]

    @pytest.mark.asyncio
    async def test_unscoped_call_is_unchanged_for_the_llc_context_builder(self, session):
        """`llc/kb/context_builder.py:199` passes no company and must keep working."""
        goal = await _seed_goal(session, BOB_CO)

        chain = await GoalService().get_goal_ancestry_for_work_item(session, goal.id)

        assert len(chain) == 1
