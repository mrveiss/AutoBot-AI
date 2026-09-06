# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cost event must move budget_spent, for the model agents actually run on.

Three independent defects produced one symptom -- dollar budgets never accruing
-- and each alone was sufficient, so fixing any one of them left it:

* the route never called the service and returned ``{"recorded": True}`` (#15859);
* the default model had no price, so the cost resolved to zero (#15860);
* a missing budget row makes the atomic UPDATE match nothing, which is logged
  and returned as the cost anyway.

Every assertion here is on the **effect** -- what ``budget_spent`` became --
rather than on a return value. The route's old response was a literal
``{"recorded": True}``, so any test reading the response passed against code
that did nothing at all.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.ssot_constants import ANTHROPIC_CLAUDE_SONNET4_6
from llc.exceptions import UnpricedModel
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.services.budget import BudgetService
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

#: The model LLC hires agents on and the Anthropic provider defaults to.
#: Imported rather than written out: a test spelling the string itself passes
#: when the default moves, which is exactly the drift #15860 was.
DEFAULT_MODEL = ANTHROPIC_CLAUDE_SONNET4_6


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


async def _seed_budget(session: AsyncSession, agent_id: str, company_id: str) -> None:
    session.add(
        LLCAgentBudget(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=agent_id,
            budget_mode=BudgetMode.DOLLARS.value,
            budget_limit=Decimal("100"),
            budget_spent=Decimal("0"),
            token_limit=None,
            tokens_spent=0,
            alert_threshold=0.8,
        )
    )
    await session.commit()


async def _spent(session: AsyncSession, agent_id: str, company_id: str) -> Decimal:
    row = (
        await session.execute(
            select(LLCAgentBudget).where(
                LLCAgentBudget.agent_id == agent_id,
                LLCAgentBudget.company_id == company_id,
            )
        )
    ).scalar_one()
    await session.refresh(row)
    return Decimal(str(row.budget_spent))


async def test_the_default_model_accrues_cost(session):  # noqa: ANN001
    """#15860: the model almost everything runs on had no price, so cost was zero.

    Asserted for the **default** specifically, not for an arbitrary priced
    model -- a test using `claude-sonnet-4-20250514` passes throughout the
    defect, because that one was always in the table.
    """
    agent, company = "agent-a", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    cost = await BudgetService().ingest_cost_event(
        session, agent_id=agent, company_id=company, tokens_in=1_000_000, tokens_out=0, model=DEFAULT_MODEL
    )
    await session.commit()

    assert cost > 0, f"{DEFAULT_MODEL} resolved to a cost of {cost}"
    assert await _spent(session, agent, company) > Decimal("0"), "budget_spent did not move"


async def test_an_unpriced_model_refuses_rather_than_costing_nothing(session):  # noqa: ANN001
    """#15860: a cost of 0 and a cost that could not be computed are the same number.

    Refusing is safe because the table distinguishes free from unknown -- every
    local model carries an explicit zero entry -- so absence means unpriced.
    """
    agent, company = "agent-b", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    with pytest.raises(UnpricedModel):
        await BudgetService().ingest_cost_event(
            session,
            agent_id=agent,
            company_id=company,
            tokens_in=1_000,
            tokens_out=1_000,
            model="a-model-nobody-priced",
        )

    assert await _spent(session, agent, company) == Decimal("0"), "an unpriced event still moved the budget"


async def test_a_priced_free_model_still_accrues_nothing(session):  # noqa: ANN001
    """The contrast case, and the reason refusing is not over-broad.

    A local model is priced at zero deliberately. If refusal keyed on `cost == 0`
    rather than on absence from the table, this would raise -- and the fix would
    have broken every local-model deployment.
    """
    from autobot_shared.ssot_constants import LOCAL_LLAMA3

    agent, company = "agent-c", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    cost = await BudgetService().ingest_cost_event(
        session, agent_id=agent, company_id=company, tokens_in=1_000_000, tokens_out=1_000_000, model=LOCAL_LLAMA3
    )
    await session.commit()

    assert cost == Decimal("0")
    assert await _spent(session, agent, company) == Decimal("0")
