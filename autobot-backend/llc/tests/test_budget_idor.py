# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for budget.py routes (GH#12136).

llc/api/budget.py previously depended only on ``get_async_session`` — no
authentication and no tenant-authorization dependency — allowing an
unauthenticated caller to provision/read/mutate ANY agent's budget by
supplying an arbitrary ``agent_id``/``company_id`` (missing-authentication +
IDOR). Uses the same in-memory-SQLite harness as test_budget_provision.py so
the real ORM-derived company_id is exercised (not a mock).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole

_FIXED_USER_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
_OTHER_ORG = str(uuid.uuid4())


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


def _make_app(session_factory, caller_org_id: str, is_platform_admin: bool = False):  # noqa: ANN001, ANN201
    """Build a FastAPI app wiring only the budget routers, with a non-admin
    tenant context fixed to *caller_org_id* (or a platform-admin bypass)."""
    from fastapi import FastAPI

    from llc.api import budget as budget_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    application = FastAPI()
    application.include_router(budget_api.router, prefix="/api/llc")
    application.include_router(budget_api.cost_events_router, prefix="/api/llc")
    application.include_router(budget_api.costs_by_model_router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_async_session] = _override_session

    def _override_current_user() -> dict:
        return {"id": str(_FIXED_USER_ID), "user_id": str(_FIXED_USER_ID)}

    def _override_tenant() -> TenantContext:
        return TenantContext(
            org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
        )

    from api.user_management.dependencies import (
        get_current_user,
        get_tenant_context,
        require_org_context,
    )

    application.dependency_overrides[get_current_user] = _override_current_user
    application.dependency_overrides[get_tenant_context] = _override_tenant
    application.dependency_overrides[require_org_context] = _override_tenant

    return application


@pytest_asyncio.fixture
async def client_factory(session_factory):  # noqa: ANN001, ANN201
    """Return a factory building an httpx client scoped to a given caller org."""

    async def _make(caller_org_id: str, is_platform_admin: bool = False) -> httpx.AsyncClient:
        app = _make_app(session_factory, caller_org_id, is_platform_admin)
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return _make


async def _insert_agent(session_factory, company_id: str) -> str:  # noqa: ANN001
    agent_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name="Test Agent",
                org_role=OrgRole.WORKER.value,
                company_id=uuid.UUID(company_id),
            )
        )
        await session.commit()
    return agent_id


@pytest.mark.asyncio
async def test_provision_own_company_returns_201(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    client = await client_factory(company_id)
    resp = await client.post(f"/api/llc/budget/{agent_id}", json={})
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_provision_cross_tenant_returns_404(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    client = await client_factory(_OTHER_ORG)
    resp = await client.post(f"/api/llc/budget/{agent_id}", json={})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_get_budget_own_company_returns_200(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    owner_client = await client_factory(company_id)
    prov = await owner_client.post(f"/api/llc/budget/{agent_id}", json={})
    assert prov.status_code == 201, prov.text

    resp = await owner_client.get(f"/api/llc/budget/{agent_id}")
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_get_budget_cross_tenant_returns_404(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    owner_client = await client_factory(company_id)
    prov = await owner_client.post(f"/api/llc/budget/{agent_id}", json={})
    assert prov.status_code == 201, prov.text

    other_client = await client_factory(_OTHER_ORG)
    resp = await other_client.get(f"/api/llc/budget/{agent_id}")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_update_limit_cross_tenant_returns_404(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    owner_client = await client_factory(company_id)
    prov = await owner_client.post(f"/api/llc/budget/{agent_id}", json={})
    assert prov.status_code == 201, prov.text

    other_client = await client_factory(_OTHER_ORG)
    resp = await other_client.patch(f"/api/llc/budget/{agent_id}/limit", json={"budget_limit": "5.00"})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_update_limit_own_company_returns_200(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    owner_client = await client_factory(company_id)
    prov = await owner_client.post(f"/api/llc/budget/{agent_id}", json={})
    assert prov.status_code == 201, prov.text

    resp = await owner_client.patch(f"/api/llc/budget/{agent_id}/limit", json={"budget_limit": "5.00"})
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["budget_limit"]) == Decimal("5.00")


@pytest.mark.asyncio
async def test_list_budgets_cross_tenant_returns_404(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    owner_client = await client_factory(company_id)
    prov = await owner_client.post(f"/api/llc/budget/{agent_id}", json={})
    assert prov.status_code == 201, prov.text

    other_client = await client_factory(_OTHER_ORG)
    resp = await other_client.get("/api/llc/budget", params={"company_id": company_id})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_list_budgets_own_company_returns_200(client_factory, session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    agent_id = await _insert_agent(session_factory, company_id)
    owner_client = await client_factory(company_id)
    prov = await owner_client.post(f"/api/llc/budget/{agent_id}", json={})
    assert prov.status_code == 201, prov.text

    resp = await owner_client.get("/api/llc/budget", params={"company_id": company_id})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
