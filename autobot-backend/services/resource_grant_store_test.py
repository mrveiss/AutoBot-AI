# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import services.resource_grant_store as store  # dotted import bypasses the MagicMock services stub

from autobot_shared.scoping.visibility import Principal
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
async def test_grant_then_has_grant_for_user(db_session):
    await store.grant(db_session, "skill", "s1", "user", "u1", "use", None)
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s1", p) is True
    other = Principal(user_id="u2", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s1", other) is False


@pytest.mark.asyncio
async def test_group_grant_matches_member(db_session):
    await store.grant(db_session, "skill", "s2", "group", "g1", "use", None)
    member = Principal(user_id="u9", company_id="c1", group_ids=frozenset({"g1"}))
    assert await store.has_grant(db_session, "skill", "s2", member) is True


@pytest.mark.asyncio
async def test_grant_is_idempotent(db_session):
    await store.grant(db_session, "skill", "s3", "user", "u1", "use", None)
    await store.grant(db_session, "skill", "s3", "user", "u1", "manage", None)  # same target
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s3", p) is True


@pytest.mark.asyncio
async def test_revoke_removes_access(db_session):
    await store.grant(db_session, "skill", "s4", "user", "u1", "use", None)
    assert await store.revoke(db_session, "skill", "s4", "user", "u1") is True
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s4", p) is False
