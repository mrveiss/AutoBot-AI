# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for BudgetService (GH#8215)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.exceptions import BudgetExhausted, UnpricedModel
from llc.services.budget import BudgetService


def _make_row(spent: float, limit: float, threshold: float = 0.8) -> MagicMock:
    row = MagicMock()
    row.agent_id = "agent-001"
    row.budget_spent = Decimal(str(spent))
    row.budget_limit = Decimal(str(limit))
    row.alert_threshold = threshold
    return row


def _make_session(row: MagicMock | None = None) -> AsyncMock:
    session = AsyncMock()
    # MagicMock (not AsyncMock) so scalar_one_or_none() returns synchronously
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_ingest_accumulates_cost() -> None:
    row = _make_row(spent=0.5, limit=10.0)
    session = _make_session(row)

    svc = BudgetService()
    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        await svc.ingest_cost_event(session, "agent-001", "company-1", 100, 50, "claude-sonnet-4-6")
        await svc.ingest_cost_event(session, "agent-001", "company-1", 100, 50, "claude-sonnet-4-6")

    # session.execute called twice per ingest (UPDATE + SELECT) = 4 total
    assert session.execute.call_count == 4


@pytest.mark.asyncio
async def test_hard_stop_raises_budget_exhausted() -> None:
    row = _make_row(spent=10.5, limit=10.0)
    session = _make_session(row)

    svc = BudgetService()
    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock):
        with pytest.raises(BudgetExhausted) as exc_info:
            await svc.ingest_cost_event(session, "agent-001", "company-1", 1000, 500, "claude-sonnet-4-6")

    assert exc_info.value.agent_id == "agent-001"
    assert exc_info.value.spent > exc_info.value.limit


@pytest.mark.asyncio
async def test_alert_emitted_at_threshold() -> None:
    # 8.5 / 10.0 = 85% >= 80% threshold
    row = _make_row(spent=8.5, limit=10.0, threshold=0.8)
    session = _make_session(row)

    mock_redis_client = AsyncMock()
    mock_redis_client.publish = AsyncMock()

    svc = BudgetService()
    with patch(
        "llc.services.budget.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis_client,
    ):
        await svc.ingest_cost_event(session, "agent-001", "company-1", 0, 0, "claude-sonnet-4-6")

    mock_redis_client.publish.assert_called_once()
    call_args = mock_redis_client.publish.call_args
    assert call_args[0][0] == "llc:budget_alert"


@pytest.mark.asyncio
async def test_alert_not_emitted_below_threshold() -> None:
    # 5.0 / 10.0 = 50% < 80% threshold
    row = _make_row(spent=5.0, limit=10.0, threshold=0.8)
    session = _make_session(row)

    mock_redis_client = AsyncMock()
    mock_redis_client.publish = AsyncMock()

    svc = BudgetService()
    with patch(
        "llc.services.budget.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis_client,
    ):
        await svc.ingest_cost_event(session, "agent-001", "company-1", 0, 0, "claude-sonnet-4-6")

    mock_redis_client.publish.assert_not_called()


@pytest.mark.asyncio
async def test_check_budget_over_limit() -> None:
    row = _make_row(spent=12.0, limit=10.0, threshold=0.8)
    session = _make_session(row)

    svc = BudgetService()
    remaining, is_over, alert = await svc.check_budget(session, "agent-001", "company-1")

    assert remaining == Decimal("10.0") - Decimal("12.0")
    assert remaining < Decimal("0")
    assert is_over is True
    assert alert is True


@pytest.mark.asyncio
async def test_unknown_model_refuses_rather_than_costing_zero() -> None:
    """#15860: this test previously asserted the defect as intended behaviour.

    It required an unpriced model to cost `Decimal("0")` and the UPDATE to run
    anyway. That is exactly what made dollar budgets silently inapplicable to
    the provider default once it fell out of the pricing table -- a cost of 0
    and a cost that could not be computed are the same number, and only one of
    them is a fact.

    Inverted rather than deleted: the case still matters, and what it should
    assert is that the event is refused. Free models are unaffected because the
    table prices them at zero explicitly, so absence means unpriced, not free.
    """
    row = _make_row(spent=0.0, limit=10.0)
    session = _make_session(row)

    svc = BudgetService()
    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        with pytest.raises(UnpricedModel):
            await svc.ingest_cost_event(session, "agent-001", "company-1", 1000, 500, "unknown-model-xyz")
