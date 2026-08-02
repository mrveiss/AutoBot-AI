# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for GET /costs/by-agent-model (#13067).

Before #13067 this endpoint queried ``llc_cost_events``, a table absent from
every migration tree. The query always raised ``UndefinedTable``, caught by
a bare ``except Exception`` that logged a warning and returned ``[]`` — so
the endpoint silently returned no data in every environment, forever.

These tests use a real in-memory SQLite schema (not mocks) so a query against
a genuinely nonexistent/misnamed table fails the same way it would against
Postgres, and prove the endpoint now returns real data sourced from
``llc_agent_budgets`` — the table ``BudgetService.ingest_cost_event`` (the
actual writer) maintains.
"""

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.budget import LLCAgentBudget
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode

_FIXED_USER_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )  # canonical: ignore py-adhoc-db-engine


def _make_app(session_factory, company_id: str) -> FastAPI:  # noqa: ANN001
    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api import costs as costs_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(costs_api.router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: {
        "id": str(_FIXED_USER_ID),
        "user_id": str(_FIXED_USER_ID),
    }
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(company_id),
        user_id=_FIXED_USER_ID,
        is_platform_admin=False,
    )
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _insert_budget(
    session_factory,  # noqa: ANN001
    company_id: str,
    agent_id: str,
    *,
    tokens_spent: int,
    budget_spent: str = "1.50",
) -> None:
    async with session_factory() as session:
        session.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=company_id,
                agent_id=agent_id,
                budget_mode="dollars",
                budget_limit="100.00",
                budget_spent=budget_spent,
                tokens_spent=tokens_spent,
                alert_threshold=0.8,
            )
        )
        await session.commit()


async def _insert_agent_org_node(session_factory, company_id: str, agent_id: str, name: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                company_id=uuid.UUID(company_id),
                agent_id=agent_id,
                name=name,
                org_role="worker",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_returns_real_data_instead_of_always_empty(session_factory) -> None:  # noqa: ANN001
    """The core #13067 regression: real llc_agent_budgets rows must surface,
    not silently vanish behind a swallowed UndefinedTable."""
    company_id = str(uuid.uuid4())
    await _insert_budget(session_factory, company_id, "agent-alpha", tokens_spent=4200)

    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get("/api/llc/costs/by-agent-model", params={"company_id": company_id})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["agent_id"] == "agent-alpha"
    assert body[0]["output_tokens"] == 4200
    assert body[0]["model"] == "unknown"


@pytest.mark.asyncio
async def test_empty_when_no_budget_rows(session_factory) -> None:  # noqa: ANN001
    """No spend recorded yet must still return 200 + [] (not an error) —
    distinguishes "no data" from the pre-#13067 "always []" defect."""
    company_id = str(uuid.uuid4())

    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get("/api/llc/costs/by-agent-model", params={"company_id": company_id})

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_agent_name_enriched_from_agent_org_nodes(session_factory) -> None:  # noqa: ANN001
    """agent_name comes from agent_org_nodes.name when the agent is registered
    there, falling back to the raw agent_id slug otherwise."""
    company_id = str(uuid.uuid4())
    await _insert_budget(session_factory, company_id, "agent-beta", tokens_spent=10)
    await _insert_agent_org_node(session_factory, company_id, "agent-beta", "Beta Prime")

    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get("/api/llc/costs/by-agent-model", params={"company_id": company_id})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["agent_name"] == "Beta Prime"


@pytest.mark.asyncio
async def test_other_companys_budget_rows_are_excluded(session_factory) -> None:  # noqa: ANN001
    """Cross-tenant isolation: another company's spend must never appear."""
    company_a = str(uuid.uuid4())
    company_b = str(uuid.uuid4())
    await _insert_budget(session_factory, company_b, "agent-other-tenant", tokens_spent=999)

    async with _client(_make_app(session_factory, company_a)) as client:
        resp = await client.get("/api/llc/costs/by-agent-model", params={"company_id": company_a})

    assert resp.status_code == 200, resp.text
    assert resp.json() == []
