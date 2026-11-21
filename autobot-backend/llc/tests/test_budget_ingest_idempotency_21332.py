# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An ingest with an idempotency key charges once per (agent, key) (#21332).

The service is driven against a real file database and an in-memory stand-in for the replay store's
Redis commands, so what is asserted is the stored spend, not a mock call count.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.adapters.autobot_agent_adapter import AutoBotAgentAdapter
from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.scheduler.heartbeat_scheduler import _ingest_adapter_usage
from llc.scheduler.usage_billing import ingest_run_cost
from llc.services.budget import BudgetService
from llc.services.budget_idempotency import IngestInFlight
from llc.tests import _e2e_harness as harness
from llc.tests.test_autobot_agent_adapter import _FAKE_AGENT_PATH

AGENTS = ("agent-a", "agent-b")
LIMIT, EVENT = 100_000, 1000
_STORE = "llc.services.budget_idempotency.get_async_redis_client"


class FakeRedis:
    """The four commands the replay store issues; the two Lua scripts are told apart by their argument count."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def set(self, key, value, nx=False, ex=None):  # noqa: ANN001
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key):  # noqa: ANN001
        return self.data.get(key)

    async def eval(self, _script, _numkeys, key, *args):  # noqa: ANN001
        if self.data.get(key) != args[0]:
            return 0
        if len(args) == 1:
            del self.data[key]
        else:
            self.data[key] = args[1]
        return 1


@pytest.fixture
def redis():
    store = FakeRedis()
    with patch(_STORE, AsyncMock(return_value=store)):
        yield store


@pytest.fixture(autouse=True)
def _no_side_services():
    with (
        patch("llc.services.budget._tracker", AsyncMock()),
        patch("llc.services.budget.BudgetService._emit_alert", AsyncMock()),
    ):
        yield


@pytest_asyncio.fixture
async def factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:  # noqa: ANN001
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        f"sqlite+aiosqlite:///{tmp_path / 'budget.db'}"
    )
    await harness.create_loop_schema(engine)
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as seed:
        for slug in AGENTS:
            seed.add(
                LLCAgentBudget(
                    id=uuid.uuid4(),
                    company_id=COMPANY,
                    agent_id=slug,
                    budget_mode=BudgetMode.TOKENS.value,
                    budget_limit=Decimal("100"),
                    budget_spent=Decimal("0"),
                    token_limit=LIMIT,
                    tokens_spent=0,
                    alert_threshold=0.8,
                )
            )
        await seed.commit()
    yield maker
    await engine.dispose()


COMPANY = str(uuid.uuid4())


async def _ingest(factory, agent: str, key: str | None, tokens: int = EVENT) -> Decimal:  # noqa: ANN001
    async with factory() as session:
        return await BudgetService().ingest_cost_event(
            session, agent, COMPANY, tokens, 0, "llama3", idempotency_key=key
        )


async def _spent(factory, agent: str) -> int:  # noqa: ANN001
    async with factory() as s:
        return (
            await s.execute(select(LLCAgentBudget.tokens_spent).where(LLCAgentBudget.agent_id == agent))
        ).scalar_one()


@pytest.mark.asyncio
async def test_the_same_key_twice_charges_once_and_returns_the_first_result(factory, redis) -> None:  # noqa: ANN001
    first = await _ingest(factory, "agent-a", "run-1")
    second = await _ingest(factory, "agent-a", "run-1", tokens=EVENT * 7)  # a repeat's payload is ignored
    assert second == first
    assert await _spent(factory, "agent-a") == EVENT


@pytest.mark.asyncio
async def test_different_keys_charge_twice(factory, redis) -> None:  # noqa: ANN001
    await _ingest(factory, "agent-a", "run-1")
    await _ingest(factory, "agent-a", "run-2")
    assert await _spent(factory, "agent-a") == 2 * EVENT


@pytest.mark.asyncio
async def test_no_key_keeps_the_old_behaviour(factory, redis) -> None:  # noqa: ANN001
    await _ingest(factory, "agent-a", None)
    await _ingest(factory, "agent-a", None)
    assert await _spent(factory, "agent-a") == 2 * EVENT
    assert redis.data == {}


@pytest.mark.asyncio
async def test_keys_are_per_agent(factory, redis) -> None:  # noqa: ANN001
    await _ingest(factory, "agent-a", "shared")
    await _ingest(factory, "agent-b", "shared")
    assert (await _spent(factory, "agent-a"), await _spent(factory, "agent-b")) == (EVENT, EVENT)


@pytest.mark.asyncio
async def test_a_repeat_of_a_hard_stop_refuses_again_without_charging(factory, redis) -> None:  # noqa: ANN001
    with pytest.raises(BudgetExhausted):
        await _ingest(factory, "agent-a", "big", tokens=LIMIT + 1)
    spent = await _spent(factory, "agent-a")
    with pytest.raises(BudgetExhausted):
        await _ingest(factory, "agent-a", "big", tokens=LIMIT + 1)
    assert await _spent(factory, "agent-a") == spent == LIMIT + 1


@pytest.mark.asyncio
async def test_a_failed_charge_releases_the_key_so_the_retry_runs(factory, redis) -> None:  # noqa: ANN001
    with patch("llc.services.budget._record_event", AsyncMock(side_effect=RuntimeError("db down"))):
        with pytest.raises(RuntimeError):
            await _ingest(factory, "agent-a", "run-1")
    await _ingest(factory, "agent-a", "run-1")
    assert await _spent(factory, "agent-a") == EVENT


@pytest.mark.asyncio
async def test_a_concurrent_duplicate_is_refused_while_the_first_is_in_flight(factory, redis) -> None:  # noqa: ANN001
    from autobot_shared.idempotency import claim, storage_key

    held = storage_key(f"{COMPANY}:agent-a", "POST", "budget.ingest_cost_event", "run-1")
    await claim(redis, held)  # the first caller holds the claim and has not completed
    with pytest.raises(IngestInFlight):
        await _ingest(factory, "agent-a", "run-1")
    assert await _spent(factory, "agent-a") == 0


@pytest.mark.asyncio
async def test_redis_down_charges_without_dedupe(factory) -> None:  # noqa: ANN001
    with patch(_STORE, AsyncMock(side_effect=ConnectionError("down"))):
        await _ingest(factory, "agent-a", "run-1")
        await _ingest(factory, "agent-a", "run-1")
    assert await _spent(factory, "agent-a") == 2 * EVENT  # never silently skipped


@pytest.mark.asyncio
async def test_the_native_adapter_passes_its_run_id_as_the_key() -> None:
    service = MagicMock(ingest_cost_event=AsyncMock())
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH}, budget_session_factory=lambda: session)
    response = SimpleNamespace(metadata={"prompt_tokens": 3, "completion_tokens": 2, "model": "m"})
    with patch("llc.services.accessors.get_budget_service", return_value=service):
        await adapter._forward_cost("run-77", response, {"agent_id": "a", "company_id": COMPANY})
    assert service.ingest_cost_event.await_args.kwargs["idempotency_key"] == "run-77"


@pytest.mark.asyncio
async def test_the_scheduler_passes_the_run_id_as_the_key() -> None:
    service = MagicMock(ingest_cost_event=AsyncMock())
    result = SimpleNamespace(billing="api", tokens_in=3, tokens_out=2)
    await ingest_run_cost(service, MagicMock(), result, "a", COMPANY, (3, 2), "m", "ext-9")
    assert service.ingest_cost_event.await_args.kwargs["idempotency_key"] == "ext-9"

    session = MagicMock(commit=AsyncMock())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    hbs = "llc.scheduler.heartbeat_scheduler"
    with (
        patch(f"{hbs}.get_async_session_factory", return_value=lambda: session),
        patch(f"{hbs}.ingest_run_cost", AsyncMock()) as ingest,
    ):
        await _ingest_adapter_usage({"agent_id": "a", "company_id": COMPANY, "model": "m"}, result, "ext-9")
    assert ingest.await_args.args[-1] == "ext-9"
