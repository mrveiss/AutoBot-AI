# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A STORED ``token_limit=0`` blocks on every enforcement path (#20930, owner decision).

NULL means no token limit; a legacy stored 0 means blocked. One helper
(``token_limit_blocks``) carries the rule for check_budget, the watchdog and the tracker.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.budget import LLCAgentBudget, token_limit_blocks
from llc.models.enums import BudgetMode
from llc.scheduler.budget_watchdog import BudgetWatchdog
from llc.services.agent_budget_tracker import AgentBudgetState
from llc.services.budget import BudgetService
from llc.tests import _e2e_harness as harness


def test_helper_null_is_unlimited_zero_blocks() -> None:
    assert token_limit_blocks(0, None) is False
    assert token_limit_blocks(0, 0) is True
    assert token_limit_blocks(5, 0) is True
    assert token_limit_blocks(5, 5) is False
    assert token_limit_blocks(6, 5) is True


@pytest_asyncio.fixture
async def session():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await eng.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens_spent", [0, 7])
async def test_check_budget_blocks_a_stored_zero(session: AsyncSession, tokens_spent: int) -> None:
    agent_id, company_id = f"za-{uuid.uuid4().hex[:8]}", str(uuid.uuid4())
    session.add(
        LLCAgentBudget(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=agent_id,
            budget_mode=BudgetMode.TOKENS.value,
            budget_limit=Decimal("100"),
            budget_spent=Decimal("0"),
            token_limit=0,
            tokens_spent=tokens_spent,
            alert_threshold=0.8,
        )
    )
    await session.commit()
    _, is_over, _ = await BudgetService().check_budget(session, agent_id, company_id)
    assert is_over is True


@pytest.mark.asyncio
async def test_watchdog_hard_stops_a_stored_zero() -> None:
    row = MagicMock()
    row.budget_mode = BudgetMode.TOKENS.value
    row.token_limit = 0
    row.tokens_spent = 0
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session.execute.return_value = result
    watchdog = BudgetWatchdog(poll_interval=9999)
    with patch.object(watchdog, "_hard_stop_agent", new=AsyncMock()) as stop:
        await watchdog._check_agent_budgets(session)
    stop.assert_awaited_once_with(session, row)


@pytest.mark.parametrize("tokens_spent", [0, 7])
def test_tracker_state_blocks_a_stored_zero(tokens_spent: int) -> None:
    state = AgentBudgetState(
        agent_id="a",
        company_id="c",
        budget_mode="tokens",
        budget_spent=0.0,
        budget_limit=100.0,
        tokens_spent=tokens_spent,
        token_limit=0,
        alert_threshold=0.8,
    )
    assert state.is_over_limit is True
