# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for token-based budget mode (GH#8997)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.services.budget import BudgetService


@pytest.fixture
async def budget_service():
    """Create a BudgetService instance."""
    return BudgetService()


@pytest.fixture
async def test_agent_id():
    """Generate a unique agent ID for testing."""
    return f"test-agent-{uuid.uuid4()}"


@pytest.fixture
async def company_id():
    """Generate a unique company ID for testing."""
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_token_mode_budget_enforcement(
    session: AsyncSession,
    budget_service: BudgetService,
    test_agent_id: str,
    company_id: str,
):
    """Test token-based budget enforcement (GH#8997)."""
    # Create a token-mode budget with 1000 token limit
    budget = LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=test_agent_id,
        budget_mode=BudgetMode.TOKENS.value,
        budget_limit=Decimal("100.00"),  # Dollar limit (not enforced in token mode)
        budget_spent=Decimal("0"),
        token_limit=1000,
        tokens_spent=0,
        alert_threshold=0.8,
    )
    session.add(budget)
    await session.commit()

    # Ingest 500 tokens (under limit)
    cost = await budget_service.ingest_cost_event(
        session, test_agent_id, tokens_in=300, tokens_out=200, model="claude-sonnet-4-6"
    )

    # Verify cost was calculated (for analytics)
    assert cost > Decimal("0")

    # Check budget status
    remaining, is_over, alert = await budget_service.check_budget(session, test_agent_id)
    assert remaining == Decimal("500")  # 1000 - 500 tokens
    assert not is_over
    assert not alert  # 500/1000 = 50% < 80% threshold

    # Ingest more tokens to trigger alert (850 total, 85%)
    await budget_service.ingest_cost_event(
        session, test_agent_id, tokens_in=200, tokens_out=150, model="claude-sonnet-4-6"
    )

    remaining, is_over, alert = await budget_service.check_budget(session, test_agent_id)
    assert remaining == Decimal("150")  # 1000 - 850 tokens
    assert not is_over
    assert alert  # 850/1000 = 85% > 80% threshold

    # Ingest tokens to exceed limit (1200 total)
    with pytest.raises(BudgetExhausted):
        await budget_service.ingest_cost_event(
            session, test_agent_id, tokens_in=200, tokens_out=150, model="claude-sonnet-4-6"
        )


@pytest.mark.asyncio
async def test_dollar_mode_budget_enforcement(
    session: AsyncSession,
    budget_service: BudgetService,
    test_agent_id: str,
    company_id: str,
):
    """Test dollar-based budget enforcement still works (GH#8215)."""
    # Create a dollar-mode budget with $10 limit
    budget = LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=test_agent_id,
        budget_mode=BudgetMode.DOLLARS.value,
        budget_limit=Decimal("10.00"),
        budget_spent=Decimal("0"),
        token_limit=None,  # Not used in dollar mode
        tokens_spent=0,
        alert_threshold=0.8,
    )
    session.add(budget)
    await session.commit()

    # Ingest tokens worth ~$5
    # claude-sonnet-4-6: $3/1M input, $15/1M output
    # 1M input + 200k output = $3 + $3 = $6
    cost = await budget_service.ingest_cost_event(
        session, test_agent_id, tokens_in=1_000_000, tokens_out=200_000, model="claude-sonnet-4-6"
    )

    assert cost == Decimal("6.00")

    # Check budget status
    remaining, is_over, alert = await budget_service.check_budget(session, test_agent_id)
    assert remaining == Decimal("4.00")  # $10 - $6
    assert not is_over
    assert not alert  # $6/$10 = 60% < 80% threshold

    # Ingest more to exceed limit
    with pytest.raises(BudgetExhausted):
        await budget_service.ingest_cost_event(
            session, test_agent_id, tokens_in=1_000_000, tokens_out=500_000, model="claude-sonnet-4-6"
        )


@pytest.mark.asyncio
async def test_mode_switch(
    session: AsyncSession,
    budget_service: BudgetService,
    test_agent_id: str,
    company_id: str,
):
    """Test switching between budget modes (GH#8997)."""
    # Start with dollar mode
    budget = LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=test_agent_id,
        budget_mode=BudgetMode.DOLLARS.value,
        budget_limit=Decimal("100.00"),
        budget_spent=Decimal("0"),
        token_limit=None,
        tokens_spent=0,
        alert_threshold=0.8,
    )
    session.add(budget)
    await session.commit()

    # Ingest some usage
    await budget_service.ingest_cost_event(
        session, test_agent_id, tokens_in=1000, tokens_out=500, model="claude-sonnet-4-6"
    )

    # Switch to token mode
    budget.budget_mode = BudgetMode.TOKENS.value
    budget.token_limit = 10000
    await session.commit()

    # Check budget now uses token limit
    remaining, is_over, alert = await budget_service.check_budget(session, test_agent_id)
    assert remaining == Decimal("8500")  # 10000 - 1500 tokens
    assert not is_over

    # Verify dollar tracking continues (for analytics)
    await session.refresh(budget)
    assert budget.budget_spent > Decimal("0")
    assert budget.tokens_spent == 1500


@pytest.mark.asyncio
async def test_both_modes_track_tokens(
    session: AsyncSession,
    budget_service: BudgetService,
    test_agent_id: str,
    company_id: str,
):
    """Verify both modes track tokens_spent for analytics (GH#8997)."""
    # Dollar mode agent
    budget = LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=test_agent_id,
        budget_mode=BudgetMode.DOLLARS.value,
        budget_limit=Decimal("100.00"),
        budget_spent=Decimal("0"),
        token_limit=None,
        tokens_spent=0,
        alert_threshold=0.8,
    )
    session.add(budget)
    await session.commit()

    # Ingest tokens
    await budget_service.ingest_cost_event(
        session, test_agent_id, tokens_in=1000, tokens_out=500, model="claude-sonnet-4-6"
    )

    # Verify tokens_spent is tracked even in dollar mode
    await session.refresh(budget)
    assert budget.tokens_spent == 1500
    assert budget.budget_spent > Decimal("0")
