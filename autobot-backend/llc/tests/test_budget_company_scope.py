# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A budget slug belongs to a company, not to the installation (#15812).

Two properties, and both need proving because each is trivially satisfiable
without the other:

* two companies **can** hold the same slug — the constraint was relaxed;
* one company's slug **cannot** reach another's row — every read and write is
  scoped.

Relaxing the constraint without the scoping would be strictly worse than the
leak it fixes: a bare ``WHERE agent_id = :slug`` would start returning
*whichever* company's row the database happened to hold, and would still return
exactly one row, so nothing would look wrong. That is why the enforcement tests
here outnumber the constraint test.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.scheduler.budget_watchdog import BudgetWatchdog
from llc.services.budget import BudgetService
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode

SLUG = "shared-slug"


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s


def _budget(agent_id: str, company_id: str, spent: float = 0.0) -> LLCAgentBudget:
    return LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=agent_id,
        budget_mode=BudgetMode.DOLLARS.value,
        budget_limit=Decimal("100"),
        budget_spent=Decimal(str(spent)),
        token_limit=None,
        tokens_spent=0,
        alert_threshold=0.8,
    )


async def _two_companies(session: AsyncSession) -> tuple[str, str]:
    """Seed the same slug under two companies. Returns (company_a, company_b)."""
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    session.add(_budget(SLUG, a, spent=10.0))
    session.add(_budget(SLUG, b, spent=90.0))
    await session.commit()
    return a, b


class TestTheConstraint:
    @pytest.mark.asyncio
    async def test_two_companies_can_hold_the_same_slug(self, session: AsyncSession) -> None:
        """Against the previous global constraint this raises IntegrityError."""
        a, b = await _two_companies(session)

        rows = (await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == SLUG))).scalars().all()

        assert {r.company_id for r in rows} == {a, b}

    @pytest.mark.asyncio
    async def test_one_company_still_cannot_hold_it_twice(self, session: AsyncSession) -> None:
        """The control. Without it, the test above passes against no constraint at all."""
        company = str(uuid.uuid4())
        session.add(_budget(SLUG, company))
        await session.commit()

        session.add(_budget(SLUG, company))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


class TestNoLookupCrossesTheBoundary:
    @pytest.mark.asyncio
    async def test_a_read_sees_only_its_own_company(self, session: AsyncSession) -> None:
        a, b = await _two_companies(session)
        svc = BudgetService()

        remaining_a, _, _ = await svc.check_budget(session, SLUG, a)
        remaining_b, _, _ = await svc.check_budget(session, SLUG, b)

        # Distinct values, each matching the row it was asked for: 100 - 10 and 100 - 90.
        assert (remaining_a, remaining_b) == (Decimal("90"), Decimal("10"))

    @pytest.mark.asyncio
    async def test_a_charge_lands_on_one_company_only(self, session: AsyncSession) -> None:
        """The raw UPDATE is the sharpest case: unscoped, it charges every company at once."""
        a, b = await _two_companies(session)

        await BudgetService().ingest_cost_event(session, SLUG, a, 1000, 500, "claude-sonnet-4-6")

        # The charge is a raw UPDATE, so the instances loaded above are stale in the
        # identity map. Expire them or the assertion reads pre-charge values and
        # passes whether or not the UPDATE was scoped.
        session.expire_all()

        rows = {
            r.company_id: r
            for r in (await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == SLUG)))
            .scalars()
            .all()
        }
        # Asserted on tokens_spent, which the UPDATE always increments, rather than on
        # budget_spent, which stays 0 for a model missing from the pricing table
        # (#15860). A dollar assertion here would pass for the wrong reason.
        assert rows[a].tokens_spent == 1500, "the charge did not reach the named company"
        assert rows[b].tokens_spent == 0, "another company's budget was charged"

    @pytest.mark.asyncio
    async def test_provisioning_is_per_company(self, session: AsyncSession) -> None:
        """A slug taken elsewhere must not read as taken here — that is the oracle itself."""
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        session.add(_budget(SLUG, a))
        await session.commit()

        row, created = await BudgetService().provision_budget(session, SLUG, b)

        assert created is True, "a slug held by another company blocked provisioning"
        # `created` alone discriminates against the old global constraint but not
        # against landing the row under the wrong company, which is the property
        # this test is named for.
        assert str(row.company_id) == b, "the provisioned row landed under the wrong company"


class TestHardStopPausesTheRightNode:
    """`_pause_agent` writes to `agent_org_nodes`, which #15812 does NOT scope.

    That table keeps `agent_id` globally unique (`models/agent_org.py:29`) while
    this change makes the budget slug unique only *per company*. So two
    companies can hold budget slug ``s`` while exactly one org node answers to
    it, and an unscoped pause would stop whichever company's agent happens to
    own that node. The company predicate is the guard against that.

    Its cost is the NULL case: `20260523_037` added `company_id` nullable on
    purpose and nothing backfills it (#15858), so a strict `= :uuid` would match
    no row, pause nothing, and let a blown budget keep spending — silently, since
    a zero-row UPDATE raises nothing. These two tests pin both halves; a fix that
    satisfies one and not the other is the failure mode being guarded.
    """

    @staticmethod
    def _node(agent_id: str, company_id: str | None):
        return AgentOrgNode(
            id=uuid.uuid4(),
            agent_id=agent_id,
            name=agent_id,
            org_role="worker",
            status="active",
            company_id=uuid.UUID(company_id) if company_id else None,
        )

    async def _pause(self, engine, agent_id: str, company_id: str) -> None:
        factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
            engine, expire_on_commit=False, class_=AsyncSession
        )
        with patch("llc.scheduler.budget_watchdog.get_async_session_factory", return_value=factory):
            await BudgetWatchdog()._pause_agent(agent_id, company_id)

    @staticmethod
    async def _status(engine, agent_id: str) -> str:
        factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
            engine, expire_on_commit=False, class_=AsyncSession
        )
        async with factory() as s:
            return (
                await s.execute(select(AgentOrgNode.status).where(AgentOrgNode.agent_id == agent_id))
            ).scalar_one()

    @pytest.mark.asyncio
    async def test_an_unscoped_node_is_still_paused(self, engine, session: AsyncSession) -> None:
        """The regression #15858's absent backfill would otherwise cause."""
        a = str(uuid.uuid4())
        session.add(self._node("legacy-agent", None))
        await session.commit()
        # Closed before the pause: the engine is an in-memory SQLite on a
        # StaticPool, so every session shares one connection and overlapping
        # transactions on it would fail for reasons unrelated to the property
        # under test.
        await session.close()

        await self._pause(engine, "legacy-agent", a)

        assert await self._status(engine, "legacy-agent") == "inactive", (
            "an org node with no company_id was not paused; the budget hard stop "
            "is disabled for every agent the #15858 backfill has not reached"
        )

    @pytest.mark.asyncio
    async def test_another_companys_node_is_left_running(self, engine, session: AsyncSession) -> None:
        """The property the company predicate exists for."""
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        session.add(self._node("their-agent", b))
        await session.commit()
        await session.close()

        await self._pause(engine, "their-agent", a)

        assert await self._status(engine, "their-agent") == "active", (
            "company a's blown budget paused an agent belonging to company b"
        )
