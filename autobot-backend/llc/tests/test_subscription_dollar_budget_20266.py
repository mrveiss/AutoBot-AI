# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A subscription run records tokens and adds no dollars; a token limit still holds (#20266)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.models.company_os_cost import CompanyOsCostEvent
from llc.models.enums import BudgetMode
from llc.scheduler.dispatch_gate import BUDGET_EXHAUSTED, dispatch_block_reason
from llc.services.budget import BudgetService
from llc.tests import _e2e_harness as harness
from llc.tests._pricing_seed import seeded_pricing_cache

_MODEL = "claude-haiku-4-5-20251001"
_REDIS = "llc.services.budget.get_async_redis_client"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(engine)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        with seeded_pricing_cache(_MODEL, 0.8, 4.0):
            yield s
    await engine.dispose()


async def _budget(session, mode: str, **fields) -> tuple[str, str]:
    agent_id, company_id = f"a-{uuid.uuid4().hex[:8]}", str(uuid.uuid4())
    row = LLCAgentBudget(
        id=uuid.uuid4(), company_id=company_id, agent_id=agent_id, budget_mode=mode, alert_threshold=0.8, **fields
    )
    session.add(row)
    await session.commit()
    return agent_id, company_id


async def _ingest(session, agent_id, company_id, tokens=(500_000, 100_000), **kw) -> Decimal:
    with patch(_REDIS, new_callable=AsyncMock, return_value=None):
        return await BudgetService().ingest_cost_event(session, agent_id, company_id, *tokens, _MODEL, **kw)


async def _gate(session, agent_id, company_id):
    with (
        patch(_REDIS, new_callable=AsyncMock, return_value=None),
        patch("llc.scheduler.dispatch_gate._pause_flag_reason", new=AsyncMock(return_value=None)),
    ):
        return await dispatch_block_reason(session, agent_id, company_id, "active")


async def _row(session, agent_id) -> LLCAgentBudget:
    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_subscription_run_adds_no_dollars_keeps_tokens_and_does_not_block_next(session) -> None:
    agent_id, company_id = await _budget(
        session, BudgetMode.DOLLARS.value, budget_limit=Decimal("0.50"), budget_spent=Decimal("0")
    )
    cost = await _ingest(
        session, agent_id, company_id, bill_dollars=False
    )  # billed, this is $0.80 against a $0.50 limit
    assert cost == Decimal("0")
    row = await _row(session, agent_id)
    assert (Decimal(str(row.budget_spent)), row.tokens_spent) == (Decimal("0"), 600_000)
    event = (await session.execute(select(CompanyOsCostEvent))).scalar_one()
    assert (event.tokens_in, event.tokens_out, Decimal(str(event.cost))) == (500_000, 100_000, Decimal("0"))
    assert await _gate(session, agent_id, company_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{}, {"bill_dollars": True}])
async def test_api_run_over_dollar_limit_still_raises_and_blocks_next(session, kwargs) -> None:
    agent_id, company_id = await _budget(session, BudgetMode.DOLLARS.value, budget_limit=Decimal("0.50"))
    with pytest.raises(BudgetExhausted):
        await _ingest(session, agent_id, company_id, **kwargs)
    assert await _gate(session, agent_id, company_id) == BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_token_limited_subscription_budget_still_stops_the_next_run(session) -> None:
    agent_id, company_id = await _budget(
        session, BudgetMode.TOKENS.value, token_limit=1000, budget_limit=Decimal("100")
    )
    with pytest.raises(BudgetExhausted):
        await _ingest(session, agent_id, company_id, tokens=(900, 400), bill_dollars=False)
    row = await _row(session, agent_id)
    assert (row.tokens_spent, Decimal(str(row.budget_spent))) == (1300, Decimal("0"))
    assert await _gate(session, agent_id, company_id) == BUDGET_EXHAUSTED
