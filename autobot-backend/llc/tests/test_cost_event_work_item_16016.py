# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``POST /agent/cost-events`` attributes each event to its work item (#16016).

``CostEvent.work_item_id`` was declared and never read, so "what did this work item
cost?" had no answer. These tests go through the route and read the rows back: the
route answers ``recorded: True`` either way, so asserting on the response proves nothing.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.api.agent_api import router
from llc.models.budget import LLCAgentBudget
from llc.models.company_os_cost import CompanyOsCostEvent
from llc.models.enums import BudgetMode, WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.tests import _e2e_harness as harness
from llc.tests._pricing_seed import seeded_pricing_cache

pytestmark = pytest.mark.asyncio

_MODEL = "claude-sonnet-4-6"
_COMPANY, _OTHER, _AGENT = str(uuid.uuid4()), str(uuid.uuid4()), "agent-16016"


@pytest.fixture(autouse=True)
def _priced():
    with seeded_pricing_cache(_MODEL, 3.00, 15.00):
        yield


@pytest_asyncio.fixture
async def factory():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    sessions = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with sessions() as s:
        s.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=_COMPANY,
                agent_id=_AGENT,
                budget_mode=BudgetMode.DOLLARS.value,
                budget_limit=Decimal("100"),
                budget_spent=Decimal("0"),
                tokens_spent=0,
                alert_threshold=0.8,
            )
        )
        await s.commit()
    yield sessions
    await eng.dispose()


@pytest_asyncio.fixture
async def client(factory):  # noqa: ANN001, ANN201
    app = FastAPI()
    app.include_router(router)
    with (
        patch("llc.api.agent_api.agent_context", return_value=(_AGENT, _COMPANY)),
        patch("user_management.database.get_async_session_factory", return_value=factory),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            yield c


async def _item(factory, company: str) -> uuid.UUID:  # noqa: ANN001
    item_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            LLCWorkItem(
                id=item_id,
                company_id=uuid.UUID(company),
                type=WorkItemType.TASK,
                identifier=f"T-{item_id.hex[:8]}",
                title="a work item",
                status=WorkItemStatus.READY,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                linked_pr_urls=[],
                requires_approval_before=[],
                backlog_position=0,
                needs_triage=False,
            )
        )
        await s.commit()
    return item_id


async def _post(client, tokens_in: int, work_item_id) -> httpx.Response:  # noqa: ANN001
    body = {"model": _MODEL, "tokens_in": tokens_in, "tokens_out": 0}
    if work_item_id is not None:
        body["work_item_id"] = str(work_item_id)
    return await client.post("/agent/cost-events", json=body)


async def _events(factory) -> list[CompanyOsCostEvent]:  # noqa: ANN001
    async with factory() as s:
        return list((await s.execute(select(CompanyOsCostEvent))).scalars())


async def _spent(factory) -> Decimal:  # noqa: ANN001
    async with factory() as s:
        return Decimal(str((await s.execute(select(func.sum(LLCAgentBudget.budget_spent)))).scalar_one()))


async def test_the_event_row_carries_the_work_item(client, factory):  # noqa: ANN001
    item = await _item(factory, _COMPANY)
    resp = await _post(client, 1_000_000, item)
    assert resp.status_code == 200, resp.text
    (event,) = await _events(factory)
    assert (event.work_item_id, event.company_id, event.agent_id) == (item, _COMPANY, _AGENT)
    assert (event.model, event.tokens_in, event.tokens_out) == (_MODEL, 1_000_000, 0)
    assert event.cost == Decimal("3") == await _spent(factory)


async def test_cost_is_answerable_per_work_item(client, factory):  # noqa: ANN001
    a, b = await _item(factory, _COMPANY), await _item(factory, _COMPANY)
    for item, tokens in ((a, 1_000_000), (a, 1_000_000), (b, 1_000_000)):
        assert (await _post(client, tokens, item)).status_code == 200
    async with factory() as s:
        per_item = dict(
            (
                await s.execute(
                    select(CompanyOsCostEvent.work_item_id, func.sum(CompanyOsCostEvent.cost)).group_by(
                        CompanyOsCostEvent.work_item_id
                    )
                )
            ).all()
        )
    assert {k: Decimal(str(v)) for k, v in per_item.items()} == {a: Decimal("6"), b: Decimal("3")}


async def test_an_event_without_an_item_is_recorded_unattributed(client, factory):  # noqa: ANN001
    assert (await _post(client, 1_000_000, None)).status_code == 200
    (event,) = await _events(factory)
    assert event.work_item_id is None
    assert await _spent(factory) == Decimal("3")


async def test_another_companys_item_is_refused_and_charges_nothing(client, factory):  # noqa: ANN001
    foreign = await _item(factory, _OTHER)
    resp = await _post(client, 1_000_000, foreign)
    assert resp.status_code == 404
    assert await _events(factory) == []
    assert await _spent(factory) == Decimal("0")


@pytest.mark.parametrize("bad", ["00000000-0000-4000-8000-000000000001", "not-a-uuid"])
async def test_an_unknown_or_malformed_item_is_refused(client, factory, bad):  # noqa: ANN001
    resp = await _post(client, 1_000_000, bad)
    assert resp.status_code == 404
    assert await _events(factory) == []
    assert await _spent(factory) == Decimal("0")
