# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The members response tells the viewer their own company role and what they may grant (#20073).

Computed from the verified tenant context, so a client can only reflect it; the writes still refuse
what the caller may not do (#19654). Calls the real route function against an in-memory database.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.user_management.models.role import Role, UserRole
from llc.api.companies import list_members
from llc.models.membership import LLCCompanyMembership
from llc.services.membership_policy import grantable_roles
from llc.services.membership_service import MembershipService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.user import User
from user_management.services import TenantContext

# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"
_ALL = ["owner", "admin", "member", "guest", "lead"]
_NO_OWNER = ["admin", "member", "guest", "lead"]


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(_SQLITE_MEMORY_URL)  # canonical: ignore py-adhoc-db-engine (test-local engine)
    tables = [User.__table__, UserRole.__table__, Role.__table__, LLCCompanyMembership.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._rebind_enums_by_value(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest.mark.parametrize(
    "role,platform_admin,expected",
    [
        ("owner", False, _ALL),
        ("admin", False, _NO_OWNER),
        ("member", False, []),
        ("guest", False, []),
        ("lead", False, []),
        (None, False, []),
        (None, True, _ALL),
        ("member", True, _ALL),
    ],
)
def test_grantable_roles_follow_the_policy(role, platform_admin, expected):
    assert grantable_roles(role, platform_admin=platform_admin) == expected


async def _list_as(session_factory, company_id, viewer_id, *, platform_admin=False):  # noqa: ANN001
    ctx = TenantContext(org_id=company_id, user_id=viewer_id, is_platform_admin=platform_admin)
    async with session_factory() as session:
        return await list_members(
            company_id=company_id, session=session, svc=MembershipService(), _current_user={}, ctx=ctx
        )


async def _seed(session_factory, company_id, roles: dict[uuid.UUID, str]) -> None:  # noqa: ANN001
    async with session_factory() as session:
        for uid, role in roles.items():
            session.add(User(id=uid, email=f"{uid}@example.test", username=f"u{uid.hex[:8]}", is_active=True))
            session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company_id, user_id=uid, role=role))
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,grantable", [("owner", _ALL), ("admin", _NO_OWNER), ("member", []), ("guest", []), ("lead", [])]
)
async def test_each_row_carries_the_callers_own_role_and_grantable_roles(
    session_factory, role, grantable
):  # noqa: ANN001
    company, viewer, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {viewer: role, other: "owner" if role != "owner" else "member"})

    rows = await _list_as(session_factory, company, viewer)

    assert len(rows["members"]) == 2
    assert rows["viewer_role"] == role
    assert rows["viewer_grantable_roles"] == grantable
    assert all("viewer_role" not in r and "viewer_can_manage" not in r for r in rows["members"])


@pytest.mark.asyncio
async def test_a_platform_admin_outside_the_company_may_grant_everything(session_factory):  # noqa: ANN001
    company, member = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {member: "owner"})

    rows = await _list_as(session_factory, company, uuid.uuid4(), platform_admin=True)

    assert rows["viewer_role"] is None
    assert rows["viewer_grantable_roles"] == _ALL


@pytest.mark.asyncio
async def test_the_role_is_the_callers_not_another_members(session_factory):  # noqa: ANN001
    company, owner, plain = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {owner: "owner", plain: "member"})

    rows = await _list_as(session_factory, company, plain)

    assert rows["viewer_role"] == "member"
    assert rows["viewer_grantable_roles"] == []


@pytest.mark.asyncio
async def test_a_platform_admin_with_no_membership_can_manage(session_factory):  # noqa: ANN001
    """#20542: the CEO routes let a platform admin through, so the flag must say so."""
    company, member = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {member: "owner"})

    rows = await _list_as(session_factory, company, uuid.uuid4(), platform_admin=True)

    assert rows["viewer_role"] is None
    assert rows["viewer_can_manage"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected", [("owner", True), ("admin", True), ("member", False), ("lead", False), ("guest", False)]
)
async def test_viewer_can_manage_follows_the_company_admin_gate(session_factory, role, expected):  # noqa: ANN001
    company, viewer, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {viewer: role, other: "member"})

    rows = await _list_as(session_factory, company, viewer)

    assert rows["viewer_can_manage"] is expected


@pytest.mark.asyncio
async def test_an_empty_company_keeps_the_servers_verdict_for_a_platform_admin(session_factory):  # noqa: ANN001
    """#21096: no rows used to mean no standing, so the controls the server would accept were hidden."""
    rows = await _list_as(session_factory, uuid.uuid4(), uuid.uuid4(), platform_admin=True)

    assert rows["members"] == []
    assert rows["viewer_can_manage"] is True
    assert rows["viewer_role"] is None
    assert rows["viewer_grantable_roles"] == _ALL


@pytest.mark.asyncio
async def test_an_empty_company_refuses_a_plain_viewer(session_factory):  # noqa: ANN001
    rows = await _list_as(session_factory, uuid.uuid4(), uuid.uuid4())

    assert rows["members"] == []
    assert rows["viewer_can_manage"] is False
    assert rows["viewer_grantable_roles"] == []


async def _get_over_http(session_factory, company_id, viewer_id, *, platform_admin=False):  # noqa: ANN001
    """GET the mounted route through the ASGI app, so response_model validation runs (#21096)."""
    import httpx
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api.companies import router
    from user_management.database import get_async_session

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")
    async with session_factory() as session:

        async def _session():
            yield session

        app.dependency_overrides[get_async_session] = _session
        app.dependency_overrides[get_current_user] = lambda: {"id": str(viewer_id)}
        app.dependency_overrides[require_org_context] = lambda: TenantContext(
            org_id=company_id, user_id=viewer_id, is_platform_admin=platform_admin
        )
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get(f"/api/llc/companies/{company_id}/members")


@pytest.mark.asyncio
async def test_http_populated_company_returns_the_envelope_with_role_strings(session_factory):  # noqa: ANN001
    company, owner, plain = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {owner: "owner", plain: "member"})

    resp = await _get_over_http(session_factory, company, owner)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"members", "viewer_role", "viewer_can_manage", "viewer_grantable_roles"}
    assert body["viewer_role"] == "owner"
    assert body["viewer_can_manage"] is True
    assert body["viewer_grantable_roles"] == _ALL
    assert {m["user_id"]: m["role"] for m in body["members"]} == {str(owner): "owner", str(plain): "member"}
    assert all(isinstance(m["display_name"], str) and m["display_name"] for m in body["members"])


@pytest.mark.asyncio
async def test_http_empty_company_returns_an_envelope_not_an_array(session_factory):  # noqa: ANN001
    resp = await _get_over_http(session_factory, uuid.uuid4(), uuid.uuid4(), platform_admin=True)

    assert resp.status_code == 200
    assert resp.json() == {
        "members": [],
        "viewer_role": None,
        "viewer_can_manage": True,
        "viewer_grantable_roles": _ALL,
    }
