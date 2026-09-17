# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import services.resource_grant_store as store  # dotted import bypasses the MagicMock services stub
import services.resource_visibility as rv  # dotted import bypasses the MagicMock services stub
from autobot_shared.scoping.scope_level import ScopeLevel
from autobot_shared.scoping.visibility import Principal, ResourceDescriptor, is_unreachable
from models.resource_grant import ResourceGrant


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ResourceGrant.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_can_access_uses_grant_when_scope_denies(db_session):
    await store.grant(db_session, "skill", "sX", "user", "u1", "use", None)
    rv.invalidate("skill", "sX")
    p = Principal(user_id="u1", company_id="c2", group_ids=frozenset())
    r = ResourceDescriptor(owner_id="owner", company_id="c1", scope=ScopeLevel.USER)
    assert await rv.can_access(db_session, p, "skill", "sX", r) is True


@pytest.mark.asyncio
async def test_can_access_org_scope_no_grant(db_session):
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    r = ResourceDescriptor(owner_id="owner", company_id="c1", scope=ScopeLevel.ORGANIZATION)
    assert await rv.can_access(db_session, p, "skill", "sY", r) is True


@pytest.mark.asyncio
async def test_null_scope_resource_denied_then_repaired_by_admin(db_session):
    """#15779 AC1: owner_id=None, no grant, ORGANIZATION with company_id=None
    denies a normal principal, and is repairable through repair_grant()."""
    r = ResourceDescriptor(owner_id=None, company_id=None, scope=ScopeLevel.ORGANIZATION)
    assert is_unreachable(r, has_grant=False)

    normal = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    assert await rv.can_access(db_session, normal, "knowledge_fact", "orphan-1", r) is False

    with patch("services.resource_visibility.audit_log", new=AsyncMock(return_value=True)) as audit:
        await rv.repair_grant(
            db_session,
            "knowledge_fact",
            "orphan-1",
            "user",
            "u1",
            permission="use",
            actor_user_id="admin-1",
        )
    audit.assert_awaited_once()
    assert audit.call_args.kwargs["operation"] == "resource.repair_grant"
    assert audit.call_args.kwargs["user_id"] == "admin-1"

    assert await rv.can_access(db_session, normal, "knowledge_fact", "orphan-1", r) is True


@pytest.mark.asyncio
async def test_repair_grant_is_idempotent_and_visible_to_the_named_grantee_only(db_session):
    r = ResourceDescriptor(owner_id=None, company_id=None, scope=ScopeLevel.ORGANIZATION)
    with patch("services.resource_visibility.audit_log", new=AsyncMock(return_value=True)):
        await rv.repair_grant(
            db_session, "knowledge_fact", "orphan-2", "user", "u1", permission="use", actor_user_id="admin-1"
        )
    other = Principal(user_id="u2", company_id="c1", group_ids=frozenset())
    assert await rv.can_access(db_session, other, "knowledge_fact", "orphan-2", r) is False
