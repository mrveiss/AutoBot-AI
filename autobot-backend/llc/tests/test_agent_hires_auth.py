# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Auth enforcement for the LLC agent-hires router (GH#12148).

Proves the three agent-hire routes are authenticated + tenant-scoped:
  - every route declares ``get_current_user`` (unauthenticated -> 401)
  - a non-admin caller cannot hire / list into a company that is not their org
    (cross-tenant -> 404), while a matching-org caller succeeds.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.tests import _e2e_harness as harness

_ORG_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_ORG_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_USER = uuid.UUID("11111111-1111-1111-1111-111111111111")


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


def _make_app(session_factory, *, org_id: uuid.UUID, is_platform_admin: bool):  # noqa: ANN001, ANN201
    from fastapi import FastAPI

    from llc.api import agent_hires as hires_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    application = FastAPI()
    application.include_router(hires_api.router, prefix="/api/llc")

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
        return {"id": str(_USER), "user_id": str(_USER), "username": "op", "role": "user"}

    def _override_tenant() -> TenantContext:
        return TenantContext(org_id=org_id, user_id=_USER, is_platform_admin=is_platform_admin)

    from api.user_management.dependencies import get_current_user, require_org_context

    application.dependency_overrides[get_current_user] = _override_current_user
    application.dependency_overrides[require_org_context] = _override_tenant
    return application


async def _client(app) -> httpx.AsyncClient:  # noqa: ANN001
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def test_all_hire_routes_require_authentication() -> None:
    """Every agent-hire route must resolve ``get_current_user`` (401 when unauth)."""
    from api.user_management.dependencies import get_current_user
    from llc.api import agent_hires as hires_api

    def _calls(dependant) -> set:  # noqa: ANN001
        found = {dependant.call}
        for sub in dependant.dependencies:
            found |= _calls(sub)
        return found

    routes = [r for r in hires_api.router.routes if getattr(r, "dependant", None)]
    assert routes, "no routes discovered on agent_hires router"
    for route in routes:
        assert get_current_user in _calls(route.dependant), f"route {route.path} does not enforce get_current_user"


@pytest.mark.asyncio
async def test_hire_cross_tenant_returns_404(session_factory) -> None:  # noqa: ANN001
    """A non-admin org_A caller may not hire into org_B (cross-tenant -> 404)."""
    app = _make_app(session_factory, org_id=_ORG_A, is_platform_admin=False)
    client = await _client(app)
    async with client:
        resp = await client.post(
            f"/api/llc/companies/{_ORG_B}/agent-hires",
            json={"agent_name": "Intruder"},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_create_agent_hire_cross_tenant_returns_404(session_factory) -> None:  # noqa: ANN001
    """POST /agent-hires with a body company_id outside the caller's org -> 404."""
    app = _make_app(session_factory, org_id=_ORG_A, is_platform_admin=False)
    client = await _client(app)
    async with client:
        resp = await client.post(
            "/api/llc/agent-hires",
            json={"company_id": str(_ORG_B)},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_hire_same_tenant_authorized(session_factory) -> None:  # noqa: ANN001
    """A non-admin caller hiring into their own org succeeds (201)."""
    app = _make_app(session_factory, org_id=_ORG_A, is_platform_admin=False)
    client = await _client(app)

    mock_provision = AsyncMock(
        return_value=(
            MagicMock(
                agent_id="stub",
                company_id=str(_ORG_A),
                budget_mode="dollars",
                budget_spent=Decimal("0"),
                budget_limit=Decimal("10.00"),
                token_limit=None,
                tokens_spent=0,
                alert_threshold=0.8,
            ),
            True,
        )
    )
    mock_execute = AsyncMock(return_value=MagicMock())

    async with client:
        with (
            patch("llc.api.agent_hires.BudgetService.provision_budget", mock_provision),
            patch("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute),
        ):
            resp = await client.post(
                f"/api/llc/companies/{_ORG_A}/agent-hires",
                json={"agent_name": "MyAgent"},
            )
    assert resp.status_code == 201, resp.text
