# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for GET /companies/{company_id}/costs/by-agent-model (#13330).

Before #13330 this endpoint raw-SELECTed ``hr.tokens_in`` / ``hr.tokens_out``
from ``llc_heartbeat_runs``, columns that do not exist anywhere on that model
(see ``llc/models/heartbeat_run.py``). The unguarded ``text()`` query always
raised ``UndefinedColumn``, so the endpoint 500'd in every environment.

These tests use a real in-memory SQLite schema (not mocks) so a query against
a genuinely nonexistent column fails the same way it would against Postgres,
and prove the endpoint now returns real data sourced from
``llc_agent_budgets`` — the same table ``llc/api/costs.py``'s sibling
``/costs/by-agent-model`` endpoint was fixed to use in #13067.
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
    from llc.api import budget as budget_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(budget_api.costs_by_model_router, prefix="/api/llc")

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


async def _insert_agent_org_node(
    session_factory,  # noqa: ANN001
    company_id: str,
    agent_id: str,
    name: str,
    *,
    model: str | None = None,
) -> None:
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                company_id=uuid.UUID(company_id),
                agent_id=agent_id,
                name=name,
                org_role="worker",
                model=model,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_returns_real_data_instead_of_500(session_factory) -> None:  # noqa: ANN001
    """The core #13330 regression: real llc_agent_budgets rows must surface
    with a 200, not a 500 from selecting nonexistent hr.tokens_in/tokens_out
    columns."""
    company_id = str(uuid.uuid4())
    await _insert_budget(session_factory, company_id, "agent-alpha", tokens_spent=4200, budget_spent="2.75")

    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get(f"/api/llc/companies/{company_id}/costs/by-agent-model")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["agent_id"] == "agent-alpha"
    # No agent_org_nodes row exists for this agent -- the LEFT join's NULL
    # branch must fall back to the raw agent_id slug (see
    # test_agent_name_enriched_from_agent_org_nodes for the non-NULL branch).
    assert body[0]["agent_name"] == "agent-alpha"
    # tokens_spent is an input+output COMBINED total (llc/services/budget.py's
    # total_tokens = tokens_in + tokens_out) with no record of the split, so
    # it must surface only via total_tokens -- not fabricated into
    # output_tokens, which would misrepresent it as 100% output and apply
    # the wrong per-token price to it (the #13067 precedent this mirrors).
    assert body[0]["total_tokens"] == 4200
    assert body[0]["input_tokens"] == 0
    assert body[0]["cached_input_tokens"] == 0
    assert body[0]["output_tokens"] == 0
    # Numeric(15, 6) — str(Decimal) preserves the column's declared scale,
    # matching list_cost_events's identical str(row.budget_spent) precedent
    # in this same module.
    assert body[0]["cost_usd"] == "2.750000"
    # No per-model cache-read counter exists anywhere in the schema -- must
    # not fabricate a specific hit rate.
    assert body[0]["cache_hit_rate"] is None
    assert body[0]["model"] == "unknown"
    assert body[0]["window"] == "lifetime"


@pytest.mark.asyncio
async def test_empty_when_no_budget_rows(session_factory) -> None:  # noqa: ANN001
    """No spend recorded yet must still return 200 + [] (not a 500)."""
    company_id = str(uuid.uuid4())

    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get(f"/api/llc/companies/{company_id}/costs/by-agent-model")

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
        resp = await client.get(f"/api/llc/companies/{company_id}/costs/by-agent-model")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["agent_name"] == "Beta Prime"


@pytest.mark.asyncio
async def test_model_enriched_from_agent_org_nodes(session_factory) -> None:  # noqa: ANN001
    """model comes from agent_org_nodes.model when the agent is registered
    there, falling back to "unknown" otherwise (review nit: the endpoint
    already joins agent_org_nodes for agent_name -- reading its real model
    column too costs nothing over hard-coding "unknown")."""
    company_id = str(uuid.uuid4())
    await _insert_budget(session_factory, company_id, "agent-gamma", tokens_spent=5)
    await _insert_agent_org_node(session_factory, company_id, "agent-gamma", "Gamma", model="claude-haiku-4-5")

    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get(f"/api/llc/companies/{company_id}/costs/by-agent-model")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["model"] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_other_companys_budget_rows_are_excluded(session_factory) -> None:  # noqa: ANN001
    """Cross-tenant isolation: another company's spend must never appear."""
    company_a = str(uuid.uuid4())
    company_b = str(uuid.uuid4())
    await _insert_budget(session_factory, company_b, "agent-other-tenant", tokens_spent=999)

    async with _client(_make_app(session_factory, company_a)) as client:
        resp = await client.get(f"/api/llc/companies/{company_a}/costs/by-agent-model")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []
