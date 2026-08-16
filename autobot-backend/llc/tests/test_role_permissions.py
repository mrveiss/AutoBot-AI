# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Role access settings and effective-permission resolution (#14221 step 3).

Two tests carry the weight:

``test_ending_a_tenure_withdraws_the_permissions_it_carried`` — the property
that makes offboarding safe by construction. If effective permissions were
resolved from *any* tenure rather than open ones, a departed holder would keep
every permission their role carried, and nothing else in this suite would
notice.

``test_a_plain_member_cannot_grant`` — the owner's rule, "admin creates the role
permissions". A grant path that authorises nothing looks identical to one that
authorises correctly until someone who should not have access uses it.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.role import RoleService
from llc.services.role_assignment import RoleAssignmentService
from llc.services.authz import NotAuthorisedError
from llc.services.role_permission import RolePermissionService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Permission, Role, RolePermission

_PERM_READ = "knowledge.read"
_PERM_WRITE = "knowledge.write"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        LLCRoleAssignment.__table__,
        LLCCompanyMembership.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as session:
        # resource/action are NOT NULL and are split out of the dot-style name,
        # matching how SYSTEM_PERMISSIONS seeds real rows: (name, resource,
        # action, description).
        for name in (_PERM_READ, _PERM_WRITE):
            resource, action = name.split(".", 1)
            session.add(Permission(name=name, resource=resource, action=action, description=f"{action} {resource}"))
        await session.commit()
    yield factory
    await engine.dispose()


async def _seed_admin(session_factory, company_id: uuid.UUID, role=MembershipRole.ADMIN) -> uuid.UUID:  # noqa: ANN001
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company_id, user_id=user_id, role=role.value))
        await session.commit()
    return user_id


#: Role CRUD is admin-gated too, so seeding a role needs an admin.
_ADMIN_USER = uuid.uuid4()


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
async def test_ending_a_tenure_withdraws_the_permissions_it_carried(session_factory):  # noqa: ANN001
    """Offboarding is safe by construction, not by remembering to revoke."""
    service = RolePermissionService()
    occupancy = RoleAssignmentService()
    company = uuid.uuid4()
    admin = await _seed_admin(session_factory, company)
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    holder = uuid.uuid4()

    async with session_factory() as session:
        await service.grant(
            session,
            company_id=company,
            role_id=role_id,
            permission=_PERM_READ,
            actor_user_id=admin,
        )
        tenure = await occupancy.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.USER,
            holder_id=holder,
        )
        await session.commit()
        tenure_id = tenure.id

    async with session_factory() as session:
        assert await service.effective_permissions(session, company, RoleHolderType.USER, holder) == {_PERM_READ}

    async with session_factory() as session:
        await occupancy.end_tenure(session, company, tenure_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.effective_permissions(session, company, RoleHolderType.USER, holder) == set()
        ), "a departed holder kept the permissions their role carried"
        # The grant itself is untouched — the role keeps its access for the next holder.
        assert await service.list_for_role(session, company, role_id) == [_PERM_READ]


@pytest.mark.asyncio
async def test_a_plain_member_cannot_grant(session_factory):  # noqa: ANN001
    """ "Admin creates the role permissions" — enforced in the service."""
    service = RolePermissionService()
    company = uuid.uuid4()
    member = await _seed_admin(session_factory, company, role=MembershipRole.MEMBER)
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError, match="may not perform this change"):
            await service.grant(
                session,
                company_id=company,
                role_id=role_id,
                permission=_PERM_READ,
                actor_user_id=member,
            )

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_an_admin_of_another_company_cannot_grant_here(session_factory):  # noqa: ANN001
    """Membership is per company — admin elsewhere grants nothing here."""
    service = RolePermissionService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    admin_of_b = await _seed_admin(session_factory, company_b)
    role_a = await _seed_role(session_factory, company_a, "SRE")

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError, match="not a member of company"):
            await service.grant(
                session,
                company_id=company_a,
                role_id=role_a,
                permission=_PERM_READ,
                actor_user_id=admin_of_b,
            )


@pytest.mark.asyncio
async def test_an_owner_may_grant(session_factory):  # noqa: ANN001
    service = RolePermissionService()
    company = uuid.uuid4()
    owner = await _seed_admin(session_factory, company, role=MembershipRole.OWNER)
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        assert (
            await service.grant(
                session,
                company_id=company,
                role_id=role_id,
                permission=_PERM_READ,
                actor_user_id=owner,
            )
            is True
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == [_PERM_READ]


@pytest.mark.asyncio
async def test_granting_twice_is_idempotent(session_factory):  # noqa: ANN001
    """A repeat grant reports False rather than creating a duplicate row."""
    service = RolePermissionService()
    company = uuid.uuid4()
    admin = await _seed_admin(session_factory, company)
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        assert (
            await service.grant(
                session,
                company_id=company,
                role_id=role_id,
                permission=_PERM_READ,
                actor_user_id=admin,
            )
            is True
        )
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.grant(
                session,
                company_id=company,
                role_id=role_id,
                permission=_PERM_READ,
                actor_user_id=admin,
            )
            is False
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == [_PERM_READ]


@pytest.mark.asyncio
async def test_an_unknown_permission_is_refused_not_created(session_factory):  # noqa: ANN001
    """A typo must fail loudly, not seed a permission that grants nothing."""
    service = RolePermissionService()
    company = uuid.uuid4()
    admin = await _seed_admin(session_factory, company)
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="unknown permission"):
            await service.grant(
                session,
                company_id=company,
                role_id=role_id,
                permission="knowledge.raed",
                actor_user_id=admin,
            )

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_cannot_grant_on_another_companys_role(session_factory):  # noqa: ANN001
    service = RolePermissionService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    admin_a = await _seed_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="does not exist in company"):
            await service.grant(
                session,
                company_id=company_a,
                role_id=role_b,
                permission=_PERM_READ,
                actor_user_id=admin_a,
            )


@pytest.mark.asyncio
async def test_a_system_roles_permissions_cannot_be_changed(session_factory):  # noqa: ANN001
    service = RolePermissionService()
    company = uuid.uuid4()
    admin = await _seed_admin(session_factory, company)

    async with session_factory() as session:
        system_role = Role(org_id=company, name="platform-admin", is_system=True)
        session.add(system_role)
        await session.commit()
        role_id = system_role.id

    async with session_factory() as session:
        with pytest.raises(ValueError, match="system role"):
            await service.grant(
                session,
                company_id=company,
                role_id=role_id,
                permission=_PERM_READ,
                actor_user_id=admin,
            )


@pytest.mark.asyncio
async def test_effective_permissions_union_across_several_roles(session_factory):  # noqa: ANN001
    """A holder of two roles gets the union, deduplicated."""
    service = RolePermissionService()
    occupancy = RoleAssignmentService()
    company = uuid.uuid4()
    admin = await _seed_admin(session_factory, company)
    sre = await _seed_role(session_factory, company, "SRE")
    lead = await _seed_role(session_factory, company, "Team Lead")
    holder = uuid.uuid4()

    async with session_factory() as session:
        for role_id, perm in ((sre, _PERM_READ), (lead, _PERM_READ), (lead, _PERM_WRITE)):
            await service.grant(
                session,
                company_id=company,
                role_id=role_id,
                permission=perm,
                actor_user_id=admin,
            )
        for role_id in (sre, lead):
            await occupancy.assign(
                session,
                actor_user_id=_ADMIN_USER,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.USER,
                holder_id=holder,
            )
        await session.commit()

    async with session_factory() as session:
        assert await service.effective_permissions(session, company, RoleHolderType.USER, holder) == {
            _PERM_READ,
            _PERM_WRITE,
        }


@pytest.mark.asyncio
async def test_a_contact_holder_resolves_permissions_too(session_factory):  # noqa: ANN001
    """Not all humans are users — a contact holding a role carries its access."""
    service = RolePermissionService()
    occupancy = RoleAssignmentService()
    company = uuid.uuid4()
    admin = await _seed_admin(session_factory, company)
    role_id = await _seed_role(session_factory, company, "Supplier escalation contact")
    contact = uuid.uuid4()

    async with session_factory() as session:
        await service.grant(
            session,
            company_id=company,
            role_id=role_id,
            permission=_PERM_READ,
            actor_user_id=admin,
        )
        await occupancy.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.CONTACT,
            holder_id=contact,
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.holder_may(session, company, RoleHolderType.CONTACT, contact, _PERM_READ)
        # The same id as a *user* holds nothing — the discriminator is load-bearing.
        assert not await service.holder_may(session, company, RoleHolderType.USER, contact, _PERM_READ)


@pytest.mark.asyncio
async def test_effective_permissions_are_company_scoped(session_factory):  # noqa: ANN001
    service = RolePermissionService()
    occupancy = RoleAssignmentService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    admin_b = await _seed_admin(session_factory, company_b)
    role_b = await _seed_role(session_factory, company_b, "SRE")
    holder = uuid.uuid4()

    async with session_factory() as session:
        await service.grant(
            session,
            company_id=company_b,
            role_id=role_b,
            permission=_PERM_READ,
            actor_user_id=admin_b,
        )
        await occupancy.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company_b,
            role_id=role_b,
            holder_type=RoleHolderType.USER,
            holder_id=holder,
        )
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.effective_permissions(session, company_a, RoleHolderType.USER, holder) == set()
        ), "permissions from another company leaked into this holder's set"


@pytest.mark.asyncio
async def test_revoke_removes_access_from_current_holders(session_factory):  # noqa: ANN001
    service = RolePermissionService()
    occupancy = RoleAssignmentService()
    company = uuid.uuid4()
    admin = await _seed_admin(session_factory, company)
    role_id = await _seed_role(session_factory, company, "SRE")
    holder = uuid.uuid4()

    async with session_factory() as session:
        await service.grant(
            session,
            company_id=company,
            role_id=role_id,
            permission=_PERM_READ,
            actor_user_id=admin,
        )
        await occupancy.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.USER,
            holder_id=holder,
        )
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.revoke(
                session,
                company_id=company,
                role_id=role_id,
                permission=_PERM_READ,
                actor_user_id=admin,
            )
            is True
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.effective_permissions(session, company, RoleHolderType.USER, holder) == set()


@pytest.mark.asyncio
async def test_roles_granting_is_the_audit_direction(session_factory):  # noqa: ANN001
    """Which roles carry this permission — scoped, sorted by name."""
    service = RolePermissionService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    admin_a = await _seed_admin(session_factory, company_a)
    admin_b = await _seed_admin(session_factory, company_b)
    sre = await _seed_role(session_factory, company_a, "SRE")
    lead = await _seed_role(session_factory, company_a, "Team Lead")
    theirs = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        for role_id, actor in ((sre, admin_a), (lead, admin_a)):
            await service.grant(
                session,
                company_id=company_a,
                role_id=role_id,
                permission=_PERM_READ,
                actor_user_id=actor,
            )
        await service.grant(
            session,
            company_id=company_b,
            role_id=theirs,
            permission=_PERM_READ,
            actor_user_id=admin_b,
        )
        await session.commit()

    async with session_factory() as session:
        found = await service.roles_granting(session, company_a, _PERM_READ)

    assert [r.name for r in found] == ["SRE", "Team Lead"]
