# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A native AutoBot-agent run's spend reaches the database, read back from a fresh session (#20883).

``test_native_agent_cost_charged_20883`` pins the wiring with a mocked service. This drives the
scheduler's real construction site (``_dispatch_autobot_agent`` builds the adapter and its session
scope itself) against the real ``BudgetService`` and a file SQLite database, then reads the budget
counter and the cost events from a SEPARATE session: it only sees the charge if something committed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, AsyncIterator, Dict
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.models.company_os_cost import CompanyOsCostEvent
from llc.models.enums import BudgetMode
from llc.scheduler.heartbeat_scheduler import _dispatch_autobot_agent
from llc.tests import _e2e_harness as harness

_AGENT_ID = "native-agent"
_USAGE_AGENT_PATH = "llc.tests.test_native_agent_cost_persists_20883.UsageAgent"
_TOKENS_PER_RUN = 15  # 10 prompt + 5 completion, from UsageAgent
_TOKEN_LIMIT = 20  # one run fits, the second crosses it


class _Response:
    status = "success"

    def __init__(self, metadata: Dict[str, Any]) -> None:
        self.metadata = metadata


class UsageAgent:
    """Reports 10 prompt and 5 completion tokens on a local model."""

    def __init__(self, **_: Any) -> None:
        pass

    async def process_request(self, request: Any) -> _Response:
        return _Response({"model": "llama3", "prompt_tokens": 10, "completion_tokens": 5})


@pytest_asyncio.fixture
async def factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:  # noqa: ANN001
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        f"sqlite+aiosqlite:///{tmp_path / 'native_cost.db'}"
    )
    await harness.create_loop_schema(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest_asyncio.fixture
async def company(factory) -> str:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=company_id,
                agent_id=_AGENT_ID,
                budget_mode=BudgetMode.TOKENS.value,
                budget_limit=Decimal("100"),
                budget_spent=Decimal("0"),
                token_limit=_TOKEN_LIMIT,
                tokens_spent=0,
                alert_threshold=0.99,
            )
        )
        await session.commit()
    return company_id


@pytest.fixture(autouse=True)
def _wiring(factory, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001, ANN202
    """Only the process boundaries are replaced: the run's Redis, the budget cache and the alert publish."""
    monkeypatch.setattr(
        "llc.adapters.autobot_agent_adapter.get_async_redis_client", AsyncMock(return_value=None), raising=False
    )
    with (
        patch("llc.scheduler.usage_billing.get_async_session_factory", return_value=factory),
        patch("llc.services.budget._tracker", AsyncMock()),
        patch("llc.services.budget.BudgetService._emit_alert", AsyncMock()),
    ):
        yield


async def _run(company_id: str) -> None:
    agent = {"agent_id": _AGENT_ID, "company_id": company_id, "adapter_config": {"agent_class": _USAGE_AGENT_PATH}}
    await _dispatch_autobot_agent(agent, {"title": "T"})


async def _stored(factory) -> tuple[int, int]:  # noqa: ANN001
    """(tokens_spent, cost event count) as a session that took no part in the run reads them."""
    async with factory() as fresh:
        spent = (await fresh.execute(select(LLCAgentBudget.tokens_spent))).scalar_one()
        events = (await fresh.execute(select(func.count()).select_from(CompanyOsCostEvent))).scalar_one()
    return int(spent), int(events)


@pytest.mark.asyncio
async def test_a_run_under_its_limit_records_a_cost_event_and_updates_the_counter(
    factory, company
) -> None:  # noqa: ANN001
    await _run(company)
    assert await _stored(factory) == (_TOKENS_PER_RUN, 1)


@pytest.mark.asyncio
async def test_a_run_over_its_limit_hard_stops_and_its_spend_persists(factory, company) -> None:  # noqa: ANN001
    await _run(company)
    with pytest.raises(BudgetExhausted):
        await _run(company)
    # The refused run's tokens really were spent: the counter and event survive the raise.
    assert await _stored(factory) == (2 * _TOKENS_PER_RUN, 2)
