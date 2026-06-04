# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for BudgetService (GH#8215)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.exceptions import BudgetExhausted
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
        await svc.ingest_cost_event(session, "agent-001", 100, 50, "claude-sonnet-4-6")
        await svc.ingest_cost_event(session, "agent-001", 100, 50, "claude-sonnet-4-6")

    # session.execute called twice per ingest (UPDATE + SELECT) = 4 total
    assert session.execute.call_count == 4


@pytest.mark.asyncio
async def test_hard_stop_raises_budget_exhausted() -> None:
    row = _make_row(spent=10.5, limit=10.0)
    session = _make_session(row)

    svc = BudgetService()
    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock):
        with pytest.raises(BudgetExhausted) as exc_info:
            await svc.ingest_cost_event(session, "agent-001", 1000, 500, "claude-sonnet-4-6")

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
        await svc.ingest_cost_event(session, "agent-001", 0, 0, "claude-sonnet-4-6")

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
        await svc.ingest_cost_event(session, "agent-001", 0, 0, "claude-sonnet-4-6")

    mock_redis_client.publish.assert_not_called()


@pytest.mark.asyncio
async def test_check_budget_over_limit() -> None:
    row = _make_row(spent=12.0, limit=10.0, threshold=0.8)
    session = _make_session(row)

    svc = BudgetService()
    remaining, is_over, alert = await svc.check_budget(session, "agent-001")

    assert remaining == Decimal("10.0") - Decimal("12.0")
    assert remaining < Decimal("0")
    assert is_over is True
    assert alert is True


@pytest.mark.asyncio
async def test_unknown_model_zero_cost() -> None:
    row = _make_row(spent=0.0, limit=10.0)
    session = _make_session(row)

    svc = BudgetService()
    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        cost = await svc.ingest_cost_event(session, "agent-001", 1000, 500, "unknown-model-xyz")

    assert cost == Decimal("0")
    # UPDATE was still called (with cost=0)
    assert session.execute.call_count >= 1
