# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tools attached to a role (#14221 step 4).

Two tests carry the weight:

``test_an_empty_registry_is_reported_as_such`` — tools have no table, so the
registry is the authority for "is this a real tool". If it is unpopulated, every
name looks unknown, and reporting that as "unknown tool" sends someone hunting
for a typo when the cause is startup ordering. The two cases must stay distinct.

``test_a_detached_tool_survives_being_unregistered`` — detaching deliberately
skips registry validation. Otherwise removing a tool from the registry would
strand it on every role that carried it, permanently.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Fully-qualified, matching RoleToolService._require_registered_tool (#14373):
# the bare ``tool_sdk`` path would resolve to a *different* singleton object
# than the one the service under test uses, so patching it here would be a
# no-op against production behaviour.
from autobot_shared.tool_sdk.registry import get_tool_registry
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.models.role_tool import LLCRoleTool
from llc.services.authz import NotAuthorisedError
from llc.services.role import RoleService
from llc.services.role_tool import RoleToolService, ToolRegistryUnavailable

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role

_ADMIN_USER = uuid.uuid4()
_TOOL = "llc.role_tool_fixture"


class _FakeMeta:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def registry(monkeypatch):  # noqa: ANN001, ANN201
    """Control what the registry reports, without registering real tools.

    Patches ``list_tools`` on the live singleton rather than swapping the
    accessor, so the service exercises the same object it uses in production.
    """
    live = get_tool_registry()
    names: list[str] = [_TOOL]
    monkeypatch.setattr(live, "list_tools", lambda **_: [_FakeMeta(n) for n in names])
    return names


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [Role.__table__, LLCCompanyMembership.__table__, LLCRoleTool.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _grant_admin(session_factory, company_id: uuid.UUID) -> None:  # noqa: ANN001
    async with session_factory() as session:
        existing = await session.execute(
            sa.select(LLCCompanyMembership.id).where(
                LLCCompanyMembership.company_id == company_id,
                LLCCompanyMembership.user_id == _ADMIN_USER,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=_ADMIN_USER,
                role=MembershipRole.ADMIN.value,
            )
        )
        await session.commit()


async def _seed_role(session_factory, company_id: uuid.UUID, name: str) -> uuid.UUID:  # noqa: ANN001
    await _grant_admin(session_factory, company_id)
    async with session_factory() as session:
        role = await RoleService().create(session, company_id=company_id, name=name, actor_user_id=_ADMIN_USER)
        await session.commit()
        return role.id


@pytest.mark.asyncio
async def test_a_registered_tool_attaches(session_factory, registry):  # noqa: ANN001
    service = RoleToolService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            tool_name=f"  {_TOOL}  ",
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == [_TOOL]


@pytest.mark.asyncio
async def test_an_unknown_tool_is_refused(session_factory, registry):  # noqa: ANN001
    service = RoleToolService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="unknown tool"):
            await service.attach(
                session,
                company_id=company,
                role_id=role_id,
                tool_name="llc.nope",
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_an_empty_registry_is_reported_as_such(session_factory, registry):  # noqa: ANN001
    """ "Nothing is registered" must not masquerade as "your tool is misspelt"."""
    service = RoleToolService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    registry.clear()

    async with session_factory() as session:
        with pytest.raises(ToolRegistryUnavailable, match="registry is empty"):
            await service.attach(
                session,
                company_id=company,
                role_id=role_id,
                tool_name=_TOOL,
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_a_detached_tool_survives_being_unregistered(session_factory, registry):  # noqa: ANN001
    """Removing a tool from the registry must not strand it on every role."""
    service = RoleToolService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            tool_name=_TOOL,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    registry.clear()  # the tool is withdrawn from the process

    async with session_factory() as session:
        assert await service.detach(session, company, role_id, _TOOL, actor_user_id=_ADMIN_USER) is True
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_a_member_cannot_attach_a_tool(session_factory, registry):  # noqa: ANN001
    service = RoleToolService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    member = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company,
                user_id=member,
                role=MembershipRole.MEMBER.value,
            )
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError, match="may not perform this change"):
            await service.attach(
                session,
                company_id=company,
                role_id=role_id,
                tool_name=_TOOL,
                actor_user_id=member,
            )

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_attaching_twice_is_refused(session_factory, registry):  # noqa: ANN001
    service = RoleToolService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            tool_name=_TOOL,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="already attached"):
            await service.attach(
                session,
                company_id=company,
                role_id=role_id,
                tool_name=_TOOL,
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_cannot_attach_to_another_companys_role(session_factory, registry):  # noqa: ANN001
    service = RoleToolService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="does not exist in company"):
            await service.attach(
                session,
                company_id=company_a,
                role_id=role_b,
                tool_name=_TOOL,
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_list_and_detach_are_company_scoped(session_factory, registry):  # noqa: ANN001
    service = RoleToolService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company_b,
            role_id=role_b,
            tool_name=_TOOL,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company_a, role_b) == []
        assert await service.detach(session, company_a, role_b, _TOOL, actor_user_id=_ADMIN_USER) is False
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company_b, role_b) == [_TOOL]
