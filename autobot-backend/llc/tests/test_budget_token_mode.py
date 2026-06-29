# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for token-based budget mode (GH#8997).

Covers:
  - Token mode: enforcement, accumulation, hard stop, alert
  - Dollar mode: unchanged behaviour (regression)
  - Mode switch: remaining recalculated in new mode
  - Both modes: tokens_spent always tracked (shadow cost)
  - API validation: mode-appropriate field guard (400)
  - Watchdog: token-mode hard stop fires; dollar-mode regression
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.services.budget import BudgetService
from llc.tests import _e2e_harness as harness

# ---------------------------------------------------------------------------
# DB fixtures — in-memory SQLite backed, reusing the e2e harness schema
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    async with session_factory() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


@pytest.fixture
def budget_service() -> BudgetService:
    return BudgetService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_budget(
    agent_id: str,
    company_id: str,
    mode: str = BudgetMode.DOLLARS.value,
    budget_limit: float = 100.0,
    token_limit: int | None = None,
    tokens_spent: int = 0,
    budget_spent: float = 0.0,
) -> LLCAgentBudget:
    return LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=agent_id,
        budget_mode=mode,
        budget_limit=Decimal(str(budget_limit)),
        budget_spent=Decimal(str(budget_spent)),
        token_limit=token_limit,
        tokens_spent=tokens_spent,
        alert_threshold=0.8,
    )


# ---------------------------------------------------------------------------
# Token mode: accumulation, alert, hard stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_mode_budget_enforcement(session: AsyncSession, budget_service: BudgetService) -> None:
    """Token-based hard stop fires when tokens_spent > token_limit (GH#8997)."""
    agent_id = f"ta-{uuid.uuid4().hex[:8]}"
    company_id = str(uuid.uuid4())
    session.add(_make_budget(agent_id, company_id, mode=BudgetMode.TOKENS.value, token_limit=1000))
    await session.commit()

    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        # 300 in + 200 out = 500 total — under 1000 limit
        cost = await budget_service.ingest_cost_event(
            session, agent_id, tokens_in=300, tokens_out=200, model="claude-haiku-4-5-20251001"
        )

    # Cost is calculated for analytics even in token mode
    assert cost > Decimal("0"), "Dollar cost should be tracked for shadow cost analytics"

    remaining, is_over, alert = await budget_service.check_budget(session, agent_id)
    assert remaining == Decimal("500")  # 1000 - 500
    assert not is_over
    assert not alert  # 500/1000 = 50% < 80%

    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        # 200 in + 150 out = 350 → total 850 (85%) — alert should fire
        await budget_service.ingest_cost_event(
            session, agent_id, tokens_in=200, tokens_out=150, model="claude-haiku-4-5-20251001"
        )

    remaining, is_over, alert = await budget_service.check_budget(session, agent_id)
    assert remaining == Decimal("150")  # 1000 - 850
    assert not is_over
    assert alert  # 850/1000 = 85% >= 80%

    # 200 in + 150 out = 350 → total 1200 > 1000 — hard stop
    with pytest.raises(BudgetExhausted):
        with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = None
            await budget_service.ingest_cost_event(
                session, agent_id, tokens_in=200, tokens_out=150, model="claude-haiku-4-5-20251001"
            )


@pytest.mark.asyncio
async def test_token_ingest_accumulation(session: AsyncSession, budget_service: BudgetService) -> None:
    """tokens_spent accumulates correctly across multiple ingest calls (GH#8997)."""
    agent_id = f"ta-{uuid.uuid4().hex[:8]}"
    company_id = str(uuid.uuid4())
    session.add(_make_budget(agent_id, company_id, mode=BudgetMode.TOKENS.value, token_limit=5000))
    await session.commit()

    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        await budget_service.ingest_cost_event(session, agent_id, 100, 50, "claude-haiku-4-5-20251001")
        await budget_service.ingest_cost_event(session, agent_id, 200, 100, "claude-haiku-4-5-20251001")

    remaining, _, _ = await budget_service.check_budget(session, agent_id)
    # 150 + 300 = 450 tokens spent; remaining = 5000 - 450
    assert remaining == Decimal("4550")


# ---------------------------------------------------------------------------
# Dollar mode: regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dollar_mode_budget_enforcement(session: AsyncSession, budget_service: BudgetService) -> None:
    """Dollar-based hard stop fires when budget_spent > budget_limit (GH#8215 regression)."""
    agent_id = f"ta-{uuid.uuid4().hex[:8]}"
    company_id = str(uuid.uuid4())
    # haiku-4-5: $0.80/1M input, $4.00/1M output
    # 1M in + 200k out = $0.80 + $0.80 = $1.60; limit $2.00 leaves $0.40 remaining
    session.add(_make_budget(agent_id, company_id, mode=BudgetMode.DOLLARS.value, budget_limit=2.0))
    await session.commit()

    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        cost = await budget_service.ingest_cost_event(
            session, agent_id, 1_000_000, 200_000, "claude-haiku-4-5-20251001"
        )

    assert cost == Decimal("1.60")
    remaining, is_over, alert = await budget_service.check_budget(session, agent_id)
    assert remaining == Decimal("0.40")  # $2.00 - $1.60
    assert not is_over
    assert alert  # 1.60/2.00 = 80% — threshold is >= 0.8, so alert fires at exactly 80%

    with pytest.raises(BudgetExhausted):
        with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = None
            # 1M in + 500k out = $0.80 + $2.00 = $2.80 → total $4.40 > $2.00 limit
            await budget_service.ingest_cost_event(session, agent_id, 1_000_000, 500_000, "claude-haiku-4-5-20251001")


# ---------------------------------------------------------------------------
# Shadow cost: tokens_spent tracked in both modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_modes_track_tokens(session: AsyncSession, budget_service: BudgetService) -> None:
    """tokens_spent is always incremented regardless of active budget mode (GH#8997)."""
    agent_id = f"ta-{uuid.uuid4().hex[:8]}"
    company_id = str(uuid.uuid4())
    session.add(_make_budget(agent_id, company_id, mode=BudgetMode.DOLLARS.value, budget_limit=100.0))
    await session.commit()

    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        await budget_service.ingest_cost_event(session, agent_id, 1000, 500, "claude-haiku-4-5-20251001")

    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
    row = result.scalar_one()
    assert row.tokens_spent == 1500  # shadow cost tracked in dollars mode
    assert row.budget_spent > Decimal("0")


@pytest.mark.asyncio
async def test_token_mode_shadow_cost_usd(session: AsyncSession, budget_service: BudgetService) -> None:
    """In token mode, budget_spent (USD) is updated as shadow cost (GH#8997)."""
    agent_id = f"ta-{uuid.uuid4().hex[:8]}"
    company_id = str(uuid.uuid4())
    session.add(_make_budget(agent_id, company_id, mode=BudgetMode.TOKENS.value, token_limit=100_000))
    await session.commit()

    with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        cost = await budget_service.ingest_cost_event(session, agent_id, 1000, 500, "claude-haiku-4-5-20251001")

    # USD shadow cost must be positive
    assert cost > Decimal("0"), "Shadow cost must be calculated and returned in token mode"

    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
    row = result.scalar_one()
    assert row.budget_spent > Decimal("0"), "budget_spent (USD shadow) must be tracked in token mode"


# ---------------------------------------------------------------------------
# Mode switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mode_switch(session_factory, budget_service: BudgetService) -> None:  # noqa: ANN001
    """Switching budget mode updates enforcement plane without losing analytics (GH#8997).

    Uses separate sessions for write and read phases to ensure the ORM identity map
    does not return stale tokens_spent after the raw-SQL UPDATE in ingest_cost_event.
    """
    agent_id = f"ta-{uuid.uuid4().hex[:8]}"
    company_id = str(uuid.uuid4())

    # Phase 1: insert the budget row in dollars mode
    async with session_factory() as s:
        s.add(_make_budget(agent_id, company_id, mode=BudgetMode.DOLLARS.value, budget_limit=100.0))
        await s.commit()

    # Phase 2: ingest tokens while in dollars mode
    async with session_factory() as s:
        with patch("llc.services.budget.get_async_redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = None
            await budget_service.ingest_cost_event(s, agent_id, 1000, 500, "claude-haiku-4-5-20251001")
        await s.commit()

    # Phase 3: switch to token mode
    async with session_factory() as s:
        result = await s.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
        budget = result.scalar_one()
        budget.budget_mode = BudgetMode.TOKENS.value
        budget.token_limit = 10000
        await s.commit()

    # Phase 4: fresh session for check_budget — sees updated DB state
    async with session_factory() as s:
        remaining, is_over, _ = await budget_service.check_budget(s, agent_id)
        assert remaining == Decimal("8500")  # 10000 - 1500 tokens
        assert not is_over

        result = await s.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
        row = result.scalar_one()
        assert row.budget_spent > Decimal("0")
        assert row.tokens_spent == 1500


# ---------------------------------------------------------------------------
# API validation: mode-appropriate field guard
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app(session_factory):  # noqa: ANN001, ANN201
    from fastapi import FastAPI

    from llc.api import budget as budget_api
    from user_management.database import get_async_session

    application = FastAPI()
    application.include_router(budget_api.router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    application.dependency_overrides[get_async_session] = _override_session
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_budget(session_factory, mode: str = "dollars") -> str:  # noqa: ANN001
    agent_id = f"va-{uuid.uuid4().hex[:8]}"
    async with session_factory() as s:
        s.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=str(uuid.uuid4()),
                agent_id=agent_id,
                budget_mode=mode,
                budget_limit=Decimal("50.00"),
                budget_spent=Decimal("0"),
                token_limit=1_000_000 if mode == "tokens" else None,
                tokens_spent=0,
                alert_threshold=0.8,
            )
        )
        await s.commit()
    return agent_id


@pytest.mark.asyncio
async def test_update_limit_rejects_token_limit_in_dollars_mode(client: httpx.AsyncClient, session_factory) -> None:
    """PATCH /limit must return 400 when token_limit is set and budget_mode is 'dollars' (GH#8997)."""
    agent_id = await _seed_budget(session_factory, mode="dollars")

    resp = await client.patch(
        f"/api/llc/budget/{agent_id}/limit",
        json={"token_limit": 500_000},
    )
    assert resp.status_code == 400, resp.text
    assert "token_limit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_limit_rejects_budget_limit_when_switching_to_tokens(
    client: httpx.AsyncClient, session_factory
) -> None:
    """PATCH /limit must return 400 when budget_limit is set and budget_mode is 'tokens' (GH#8997)."""
    agent_id = await _seed_budget(session_factory, mode="dollars")

    resp = await client.patch(
        f"/api/llc/budget/{agent_id}/limit",
        json={"budget_mode": "tokens", "budget_limit": "20.00"},
    )
    assert resp.status_code == 400, resp.text
    assert "budget_limit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_limit_accepts_token_limit_in_tokens_mode(client: httpx.AsyncClient, session_factory) -> None:
    """PATCH /limit accepts token_limit when budget_mode is 'tokens' (GH#8997)."""
    agent_id = await _seed_budget(session_factory, mode="dollars")

    with patch("llc.services.budget._tracker.get_state", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        resp = await client.patch(
            f"/api/llc/budget/{agent_id}/limit",
            json={"budget_mode": "tokens", "token_limit": 2_000_000},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["budget_mode"] == "tokens"
    assert data["token_limit"] == 2_000_000


@pytest.mark.asyncio
async def test_update_limit_accepts_budget_limit_in_dollars_mode(client: httpx.AsyncClient, session_factory) -> None:
    """PATCH /limit accepts budget_limit when budget_mode is 'dollars' (GH#8997)."""
    agent_id = await _seed_budget(session_factory, mode="dollars")

    with patch("llc.services.budget._tracker.get_state", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        resp = await client.patch(
            f"/api/llc/budget/{agent_id}/limit",
            json={"budget_limit": "75.00"},
        )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["budget_limit"]) == Decimal("75.00")


# ---------------------------------------------------------------------------
# Watchdog: token-mode hard stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_token_mode_hard_stop() -> None:
    """BudgetWatchdog fires hard_stop for a token-mode agent at 100% (GH#8997)."""
    import json
    from unittest.mock import MagicMock

    from llc.scheduler.budget_watchdog import BudgetWatchdog

    company_id = str(uuid.uuid4())
    row = LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=f"wa-{uuid.uuid4().hex[:6]}",
        budget_mode=BudgetMode.TOKENS.value,
        budget_limit=Decimal("100.00"),
        budget_spent=Decimal("0.05"),  # shadow cost
        token_limit=1000,
        tokens_spent=1200,  # over 1000 limit
        alert_threshold=0.8,
    )

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    scalars = MagicMock()
    scalars.all.return_value = [row]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session = AsyncMock()
    session.execute.return_value = execute_result

    mock_svc = MagicMock()
    mock_svc.check_budget = AsyncMock(return_value=(Decimal("-200"), True, True))

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
    assert channel == f"llc:notifications:{company_id}"
    payload = json.loads(payload_json)
    assert payload["event_type"] == "budget.hard_stop"
    assert payload["budget_mode"] == "tokens"
    assert payload["spent"] == 1200
    assert payload["shadow_cost_usd"] == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_watchdog_token_mode_soft_alert() -> None:
    """BudgetWatchdog fires soft_alert for a token-mode agent at 85% (GH#8997)."""
    import json
    from unittest.mock import MagicMock

    from llc.scheduler.budget_watchdog import BudgetWatchdog

    company_id = str(uuid.uuid4())
    row = LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=f"wa-{uuid.uuid4().hex[:6]}",
        budget_mode=BudgetMode.TOKENS.value,
        budget_limit=Decimal("100.00"),
        budget_spent=Decimal("0.03"),
        token_limit=1000,
        tokens_spent=850,  # 85% — triggers soft alert
        alert_threshold=0.8,
    )

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    scalars = MagicMock()
    scalars.all.return_value = [row]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session = AsyncMock()
    session.execute.return_value = execute_result

    with patch(
        "llc.scheduler.budget_watchdog.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        watchdog = BudgetWatchdog(poll_interval=9999)
        await watchdog._check_agent_budgets(session)

    mock_redis.publish.assert_called_once()
    _, payload_json = mock_redis.publish.call_args[0]
    payload = json.loads(payload_json)
    assert payload["event_type"] == "budget.soft_alert"
    assert payload["budget_mode"] == "tokens"


@pytest.mark.asyncio
async def test_watchdog_token_mode_under_threshold_no_alert() -> None:
    """BudgetWatchdog does NOT alert for a token-mode agent at 50% (GH#8997)."""
    from unittest.mock import MagicMock

    from llc.scheduler.budget_watchdog import BudgetWatchdog

    row = LLCAgentBudget(
        id=uuid.uuid4(),
        company_id=str(uuid.uuid4()),
        agent_id=f"wa-{uuid.uuid4().hex[:6]}",
        budget_mode=BudgetMode.TOKENS.value,
        budget_limit=Decimal("100.00"),
        budget_spent=Decimal("0.01"),
        token_limit=1000,
        tokens_spent=500,  # 50% — under 80% threshold
        alert_threshold=0.8,
    )

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    scalars = MagicMock()
    scalars.all.return_value = [row]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session = AsyncMock()
    session.execute.return_value = execute_result

    with patch(
        "llc.scheduler.budget_watchdog.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        watchdog = BudgetWatchdog(poll_interval=9999)
        await watchdog._check_agent_budgets(session)

    mock_redis.publish.assert_not_called()
