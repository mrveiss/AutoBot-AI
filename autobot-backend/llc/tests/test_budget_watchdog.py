# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for BudgetWatchdog (GH#8228)."""

import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.budget_watchdog import BudgetWatchdog


def _make_budget_row(spent: float, limit: float, company_id: str | None = None) -> MagicMock:
    row = MagicMock()
    row.agent_id = f"agent-{uuid.uuid4().hex[:6]}"
    row.company_id = company_id or str(uuid.uuid4())
    row.budget_spent = Decimal(str(spent))
    row.budget_limit = Decimal(str(limit))
    return row


def _make_agent_budget_session(rows: list) -> AsyncMock:
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    execute_result.scalar_one_or_none.side_effect = [None] * 10
    session.execute.return_value = execute_result
    return session


@pytest.mark.asyncio
async def test_soft_alert_published_at_80pct() -> None:
    """Notification published when agent reaches 80% of budget."""
    company_id = str(uuid.uuid4())
    row = _make_budget_row(spent=8.0, limit=10.0, company_id=company_id)

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    session = _make_agent_budget_session([row])

    with (
        patch(
            "llc.scheduler.budget_watchdog.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
        patch("llc.scheduler.budget_watchdog.get_async_session_factory") as mock_factory,
    ):
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = factory

        watchdog = BudgetWatchdog(poll_interval=9999)
        await watchdog._check_agent_budgets(session)

    mock_redis.publish.assert_called_once()
    channel, payload_json = mock_redis.publish.call_args[0]
    assert channel == f"llc:notifications:{company_id}"
    payload = json.loads(payload_json)
    assert payload["event_type"] == "budget.soft_alert"
    assert payload["agent_id"] == row.agent_id


@pytest.mark.asyncio
async def test_no_alert_below_80pct() -> None:
    """No notification when agent is below the 80% threshold."""
    row = _make_budget_row(spent=7.5, limit=10.0)

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    session = _make_agent_budget_session([row])

    with patch(
        "llc.scheduler.budget_watchdog.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        watchdog = BudgetWatchdog(poll_interval=9999)
        await watchdog._check_agent_budgets(session)

    mock_redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_hard_stop_at_100pct() -> None:
    """Hard-stop notification and agent pause triggered at 100%."""
    company_id = str(uuid.uuid4())
    row = _make_budget_row(spent=10.5, limit=10.0, company_id=company_id)

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    # BudgetService.check_budget returns (remaining, is_over, alert)
    mock_svc = MagicMock()
    mock_svc.check_budget = AsyncMock(return_value=(Decimal("-0.5"), True, True))

    session = _make_agent_budget_session([row])

    with (
        patch(
            "llc.scheduler.budget_watchdog.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
        patch("llc.scheduler.budget_watchdog.get_async_session_factory") as mock_factory,
    ):
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = factory

        watchdog = BudgetWatchdog(poll_interval=9999)
        watchdog._budget_svc = mock_svc
        await watchdog._check_agent_budgets(session)

    mock_redis.publish.assert_called_once()
    channel, payload_json = mock_redis.publish.call_args[0]
    payload = json.loads(payload_json)
    assert payload["event_type"] == "budget.hard_stop"


@pytest.mark.asyncio
async def test_zero_limit_skipped() -> None:
    """Agents with budget_limit=0 are not evaluated (unlimited budget)."""
    row = _make_budget_row(spent=100.0, limit=0.0)

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    session = _make_agent_budget_session([row])

    with patch(
        "llc.scheduler.budget_watchdog.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        watchdog = BudgetWatchdog(poll_interval=9999)
        await watchdog._check_agent_budgets(session)

    mock_redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_redis_unavailable_does_not_raise() -> None:
    """When Redis is None, _notify() logs a warning and returns gracefully."""
    company_id = str(uuid.uuid4())
    row = _make_budget_row(spent=8.5, limit=10.0, company_id=company_id)

    session = _make_agent_budget_session([row])

    with patch(
        "llc.scheduler.budget_watchdog.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=None,
    ):
        watchdog = BudgetWatchdog(poll_interval=9999)
        # Should not raise even with Redis unavailable
        await watchdog._check_agent_budgets(session)


def test_watchdog_start_stop() -> None:
    """BudgetWatchdog.start() creates a task; stop() cancels it."""
    import asyncio

    async def _run():
        watchdog = BudgetWatchdog(poll_interval=9999)
        with patch("llc.scheduler.budget_watchdog.get_async_session_factory"):
            watchdog.start()
            assert watchdog._task is not None
            assert not watchdog._task.done()
            watchdog.stop()
            assert not watchdog._running

    asyncio.get_event_loop().run_until_complete(_run())
