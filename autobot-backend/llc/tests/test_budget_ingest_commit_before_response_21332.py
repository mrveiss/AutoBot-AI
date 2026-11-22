# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A budget write is committed before its response is produced (#21332).

`get_async_session` commits in its teardown, which FastAPI runs after the response is sent. The route
handlers are called here directly (no teardown), and the spend is read from a SECOND connection to a
file database: it only sees the charge if the handler itself committed. Before the fix the second
session read the old remainder, which is how a caller that ingests, reads and ingests again charged twice.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.api.budget import (
    IngestRequest,
    ProvisionBudgetRequest,
    UpdateLimitRequest,
    ingest_cost,
    provision_budget,
    update_limit,
)
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole
from user_management.services import TenantContext

SLUG = "ingest-agent"
SPENT, LIMIT, EVENT = 400, 1400, 1000


@pytest_asyncio.fixture
async def factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:  # noqa: ANN001
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        f"sqlite+aiosqlite:///{tmp_path / 'budget.db'}"
    )
    await harness.create_loop_schema(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest.fixture(autouse=True)
def _no_redis():
    """The tracker cache and the alert publish are Redis; the test is about the database commit only."""
    with (
        patch("llc.services.budget._tracker", AsyncMock()),
        patch("llc.services.budget.BudgetService._emit_alert", AsyncMock()),
    ):
        yield


@pytest_asyncio.fixture
async def company(factory) -> str:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with factory() as s:
        s.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=company_id,
                agent_id=SLUG,
                budget_mode=BudgetMode.TOKENS.value,
                budget_limit=Decimal("100"),
                budget_spent=Decimal("0"),
                token_limit=LIMIT,
                tokens_spent=SPENT,
                alert_threshold=0.8,
            )
        )
        await s.commit()
    return company_id


def _ctx(company_id: str) -> TenantContext:
    return TenantContext(org_id=uuid.UUID(company_id), user_id=uuid.uuid4(), is_platform_admin=True)


async def _read(factory, column) -> object:  # noqa: ANN001
    """The stored value as a DIFFERENT session sees it."""
    async with factory() as other:
        return (await other.execute(select(column).where(LLCAgentBudget.agent_id == SLUG))).scalar_one()


@pytest.mark.asyncio
async def test_an_ingest_is_visible_to_another_session_the_moment_it_answers(factory, company) -> None:  # noqa: ANN001
    async with factory() as session:
        await ingest_cost(
            SLUG, IngestRequest(tokens_in=EVENT, tokens_out=0, model="llama3"), session, {}, _ctx(company)
        )
        # No teardown has run: only the handler's own commit makes this visible.
        assert await _read(factory, LLCAgentBudget.tokens_spent) == SPENT + EVENT


@pytest.mark.asyncio
async def test_a_limit_change_is_visible_to_another_session_the_moment_it_answers(
    factory, company
) -> None:  # noqa: ANN001
    body = UpdateLimitRequest(budget_mode="tokens", token_limit=5000)
    with (
        patch("llc.api.budget.company_requires_budget_approval", AsyncMock(return_value=False)),
        patch("llc.api.budget.BudgetService.invalidate_cache", AsyncMock()),
    ):
        async with factory() as session:
            await update_limit(SLUG, body, _Response(), session, {}, _ctx(company))
            assert await _read(factory, LLCAgentBudget.token_limit) == 5000


@pytest.mark.asyncio
async def test_a_provisioned_budget_is_visible_to_another_session_the_moment_it_answers(
    factory,
) -> None:  # noqa: ANN001
    company_id, agent = str(uuid.uuid4()), "provisioned-agent"
    async with factory() as seed:
        seed.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent,
                name="Agent",
                org_role=OrgRole.WORKER.value,
                company_id=uuid.UUID(company_id),
            )
        )
        await seed.commit()
    async with factory() as session:
        await provision_budget(agent, ProvisionBudgetRequest(), _Response(), session, {}, _ctx(company_id))
        async with factory() as other:
            found = (
                await other.execute(select(LLCAgentBudget.agent_id).where(LLCAgentBudget.agent_id == agent))
            ).scalar_one_or_none()
        assert found == agent


class _Response:
    status_code = 200
