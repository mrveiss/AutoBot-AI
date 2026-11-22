# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Legacy path-scoped workflow create delegates to the Company OS service (#21239).

Real routers and services on SQLite; only the session and the two auth dependencies are replaced.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, cast

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.company_os import router as company_os_router
from llc.api.workflows import router as legacy_router
from llc.deps import get_session
from llc.models.activity import LLCActivityLog
from llc.models.company_os import LLCProcess, LLCRoleSkill, LLCWorkflowNode, LLCWorkflowTransition
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from models.workflow import Workflow
from user_management.database import get_async_session
from user_management.models.base import Base
from user_management.models.role import Role
from user_management.services import TenantContext

COMPANY_A, COMPANY_B = uuid.uuid4(), uuid.uuid4()
ADMIN_A, MEMBER_A, PLATFORM = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
_TABLES: list[Table] = [
    cast(Table, LLCActivityLog.__table__),
    cast(Table, Role.__table__),
    cast(Table, Workflow.__table__),
    cast(Table, LLCProcess.__table__),
    cast(Table, LLCWorkflowNode.__table__),
    cast(Table, LLCWorkflowTransition.__table__),
    cast(Table, LLCRoleSkill.__table__),
    cast(Table, LLCCompanyMembership.__table__),
]
_COMPARED = ("name", "status", "source", "kind", "owner_role_id", "trigger_type", "trigger_config", "definition")


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    for table in _TABLES:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as s:
        for company, user, role in (
            (COMPANY_A, ADMIN_A, MembershipRole.ADMIN),
            (COMPANY_A, MEMBER_A, MembershipRole.MEMBER),
            (COMPANY_A, PLATFORM, MembershipRole.ADMIN),
        ):
            s.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company, user_id=user, role=role.value))
        await s.commit()
    yield maker
    await engine.dispose()


def _client(maker, org: uuid.UUID, user: uuid.UUID, platform: bool = False) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(company_os_router, prefix="/api/llc")
    app.include_router(legacy_router, prefix="/api/llc")

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_async_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=org, user_id=user, is_platform_admin=platform
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _role(maker, company: uuid.UUID) -> uuid.UUID:
    async with maker() as s:
        role = Role(id=uuid.uuid4(), org_id=company, name="sales")
        s.add(role)
        await s.commit()
        return role.id


async def _row(maker, company: uuid.UUID, wid: str) -> Workflow:
    async with maker() as s:
        return (
            await s.execute(select(Workflow).where(Workflow.company_id == company, Workflow.workflow_id == wid))
        ).scalar_one()


@pytest.mark.asyncio
async def test_non_admin_is_refused_and_admin_creates(factory):  # noqa: ANN001
    role = await _role(factory, COMPANY_A)
    body = {"workflow_id": "wf", "owner_role_id": str(role)}
    async with _client(factory, COMPANY_A, MEMBER_A) as c:
        assert (await c.post(f"/api/llc/workflows/{COMPANY_A}", json=body)).status_code == 403
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        res = await c.post(f"/api/llc/workflows/{COMPANY_A}", json=body)
        assert res.status_code == 201
        assert res.json()["kind"] == "workflow" and res.json()["owner_role_id"] == str(role)
        assert (await c.post(f"/api/llc/workflows/{COMPANY_A}", json=body)).status_code == 409
        assert (await c.post(f"/api/llc/workflows/{COMPANY_A}", json={"workflow_id": "x"})).status_code == 400


@pytest.mark.asyncio
async def test_both_routes_write_identical_rows(factory):  # noqa: ANN001
    role = await _role(factory, COMPANY_A)
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        legacy = {"workflow_id": "legacy", "name": "n", "owner_role_id": str(role)}
        assert (await c.post(f"/api/llc/workflows/{COMPANY_A}", json=legacy)).status_code == 201
        new = {**legacy, "workflow_id": "new"}
        assert (await c.post("/api/llc/company-os/workflows", json=new)).status_code == 201
    a, b = await _row(factory, COMPANY_A, "legacy"), await _row(factory, COMPANY_A, "new")
    assert {k: getattr(a, k) for k in _COMPARED} == {k: getattr(b, k) for k in _COMPARED}


@pytest.mark.asyncio
async def test_company_admin_member_creates_in_the_path_company(factory):  # noqa: ANN001
    role = await _role(factory, COMPANY_A)
    async with _client(factory, COMPANY_B, PLATFORM, platform=True) as c:
        res = await c.post(f"/api/llc/workflows/{COMPANY_A}", json={"workflow_id": "wf", "owner_role_id": str(role)})
    assert res.status_code == 201 and res.json()["company_id"] == str(COMPANY_A)
    assert (await _row(factory, COMPANY_A, "wf")).company_id == COMPANY_A


@pytest.mark.asyncio
async def test_platform_admin_without_membership_is_refused(factory):  # noqa: ANN001
    role = await _role(factory, COMPANY_A)
    stranger = uuid.uuid4()
    async with _client(factory, COMPANY_B, stranger, platform=True) as c:
        res = await c.post(f"/api/llc/workflows/{COMPANY_A}", json={"workflow_id": "wf", "owner_role_id": str(role)})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_out_of_vocabulary_status_is_422(factory):  # noqa: ANN001
    role = await _role(factory, COMPANY_A)
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        res = await c.post(
            f"/api/llc/workflows/{COMPANY_A}",
            json={"workflow_id": "wf", "owner_role_id": str(role), "status": "bogus"},
        )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_legacy_create_rejects_meta_skill(factory):  # noqa: ANN001
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        res = await c.post(f"/api/llc/workflows/{COMPANY_A}", json={"workflow_id": "m", "kind": "meta_skill"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_foreign_company_owner_role_is_refused(factory):  # noqa: ANN001
    foreign = await _role(factory, COMPANY_B)
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        res = await c.post(f"/api/llc/workflows/{COMPANY_A}", json={"workflow_id": "wf", "owner_role_id": str(foreign)})
    assert res.status_code == 404
