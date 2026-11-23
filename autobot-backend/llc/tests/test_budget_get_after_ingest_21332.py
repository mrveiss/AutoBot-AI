# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`GET /budget/{agent_id}` right after a 200 ingest always shows the post-ingest spend (#21332 AC1).

Real HTTP through the real `llc.deps.get_session` (only its session factory points at a file database): the
ingest route is on `SESSION_DEP`, so the write is committed before the 200 leaves, and every following GET
(a new request, a new session) reads it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, get_tenant_context
from llc.api import budget as budget_api
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.tests import _e2e_harness as harness
from user_management.services import TenantContext

SLUG = "ingest-agent"
SPENT, LIMIT, EVENT, READS = 400, 5000, 1000, 5
_USER = uuid.uuid4()


@pytest_asyncio.fixture
async def factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:  # noqa: ANN001
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        f"sqlite+aiosqlite:///{tmp_path / 'budget-http.db'}"
    )
    await harness.create_loop_schema(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest_asyncio.fixture
async def client(factory) -> AsyncIterator[AsyncClient]:  # noqa: ANN001
    company = uuid.uuid4()
    async with factory() as seed:
        seed.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=str(company),
                agent_id=SLUG,
                budget_mode=BudgetMode.TOKENS.value,
                budget_limit=Decimal("100"),
                budget_spent=Decimal("0"),
                token_limit=LIMIT,
                tokens_spent=SPENT,
                alert_threshold=0.8,
            )
        )
        await seed.commit()
    app = FastAPI()
    app.include_router(budget_api.router)
    ctx = TenantContext(org_id=company, user_id=_USER, is_platform_admin=False)
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER), "user_id": str(_USER)}
    app.dependency_overrides[get_tenant_context] = lambda: ctx
    with (
        patch("llc.deps.get_async_session_factory", return_value=factory),
        patch("llc.services.budget._tracker", AsyncMock()),
        patch("llc.services.budget.BudgetService._emit_alert", AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            yield c


@pytest.mark.asyncio
async def test_repeated_http_gets_right_after_a_200_ingest_always_see_the_post_ingest_value(
    client: AsyncClient,
) -> None:
    ingest = await client.post(f"/budget/{SLUG}/ingest", json={"tokens_in": EVENT, "tokens_out": 0, "model": "llama3"})
    assert ingest.status_code == 200, ingest.text
    for _ in range(READS):
        read = await client.get(f"/budget/{SLUG}")
        assert read.status_code == 200, read.text
        assert read.json()["tokens_spent"] == SPENT + EVENT
