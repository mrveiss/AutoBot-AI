# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Credential references on a role, and revocation (#14221 step 4).

The load-bearing test is ``test_revoking_a_secret_withdraws_it_from_the_role``.
Revocation is applied when *reading*, not only when attaching — so revoking a
secret removes it from every role immediately, with no sweep. An implementation
that filtered only at attach time passes every "can I attach a revoked secret?"
assertion while leaving already-attached revoked credentials reachable, which is
the one thing revocation exists to prevent.

``test_a_secret_from_another_company_cannot_be_attached`` is the second: it
exercises the single UUID/String coercion that bridges ``llc_roles`` and
``llc_secrets`` (#14312). If that conversion were wrong the predicate would
match nothing and the guard would look like it worked.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from user_management.models.role import Role

from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.models.role_credential import LLCRoleCredential
from llc.models.secret import LLCSecret
from llc.services.authz import NotAuthorisedError
from llc.services.role import RoleService
from llc.services.role_credential import RoleCredentialService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base

_ADMIN_USER = uuid.uuid4()


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [
        Role.__table__,
        LLCCompanyMembership.__table__,
        LLCRoleCredential.__table__,
        LLCSecret.__table__,
    ]
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


async def _seed_secret(  # noqa: ANN001
    session_factory, company_id: uuid.UUID, name: str, *, revoked: bool = False
) -> uuid.UUID:
    """A secret row. company_id is stored as a STRING here — that is the #14312 split."""
    secret_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCSecret(
                id=secret_id,
                company_id=str(company_id),
                name=name,
                value=b"encrypted-bytes",
                created_by_agent_id="agent-1",
                revoked_at=datetime(2026, 1, 1, tzinfo=timezone.utc) if revoked else None,
            )
        )
        await session.commit()
    return secret_id


@pytest.mark.asyncio
async def test_revoking_a_secret_withdraws_it_from_the_role(session_factory):  # noqa: ANN001
    """Revocation is honoured at read time, so it needs no sweep."""
    service = RoleCredentialService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    secret_id = await _seed_secret(session_factory, company, "stripe-key")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            secret_id=secret_id,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.list_active_for_role(session, company, role_id) == [secret_id]

    async with session_factory() as session:
        await session.execute(
            sa.update(LLCSecret)
            .where(LLCSecret.id == secret_id)
            .values(revoked_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.list_active_for_role(session, company, role_id) == []
        ), "a revoked secret was still reachable through the role"
        # The attachment row survives — the administrative view still shows it,
        # so an admin can see what was withdrawn rather than it vanishing.
        assert len(await service.list_for_role(session, company, role_id)) == 1


@pytest.mark.asyncio
async def test_a_revoked_secret_cannot_be_attached(session_factory):  # noqa: ANN001
    """Refused distinctly from 'not found' — only one means something changed."""
    service = RoleCredentialService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    secret_id = await _seed_secret(session_factory, company, "old-key", revoked=True)

    async with session_factory() as session:
        with pytest.raises(ValueError, match="is revoked"):
            await service.attach(
                session,
                company_id=company,
                role_id=role_id,
                secret_id=secret_id,
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_a_secret_from_another_company_cannot_be_attached(session_factory):  # noqa: ANN001
    """Exercises the one UUID/String coercion bridging roles and secrets (#14312)."""
    service = RoleCredentialService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_a = await _seed_role(session_factory, company_a, "SRE")
    theirs = await _seed_secret(session_factory, company_b, "their-key")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="does not exist in company"):
            await service.attach(
                session,
                company_id=company_a,
                role_id=role_a,
                secret_id=theirs,
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_the_company_coercion_actually_matches(session_factory):  # noqa: ANN001
    """The positive half of the coercion.

    Asserting only that another company's secret is refused would also pass if
    the predicate matched *nothing* — the empty-result-reads-as-clean trap. This
    proves the same code path accepts the right secret.
    """
    service = RoleCredentialService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    secret_id = await _seed_secret(session_factory, company, "ours")

    async with session_factory() as session:
        attachment = await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            secret_id=secret_id,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    assert attachment.secret_id == secret_id


@pytest.mark.asyncio
async def test_a_member_cannot_attach_a_credential(session_factory):  # noqa: ANN001
    """Credential access is an admin decision."""
    service = RoleCredentialService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    secret_id = await _seed_secret(session_factory, company, "k")
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
                secret_id=secret_id,
                actor_user_id=member,
            )

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_attaching_twice_is_refused(session_factory):  # noqa: ANN001
    service = RoleCredentialService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    secret_id = await _seed_secret(session_factory, company, "k")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            secret_id=secret_id,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="already attached"):
            await service.attach(
                session,
                company_id=company,
                role_id=role_id,
                secret_id=secret_id,
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_list_and_detach_are_company_scoped(session_factory):  # noqa: ANN001
    service = RoleCredentialService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")
    secret_b = await _seed_secret(session_factory, company_b, "k")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company_b,
            role_id=role_b,
            secret_id=secret_b,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company_a, role_b) == []
        assert await service.detach(session, company_a, role_b, secret_b, actor_user_id=_ADMIN_USER) is False
        await session.commit()

    async with session_factory() as session:
        assert len(await service.list_for_role(session, company_b, role_b)) == 1


@pytest.mark.asyncio
async def test_detach_removes_the_reference(session_factory):  # noqa: ANN001
    service = RoleCredentialService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    secret_id = await _seed_secret(session_factory, company, "k")

    async with session_factory() as session:
        await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            secret_id=secret_id,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.detach(session, company, role_id, secret_id, actor_user_id=_ADMIN_USER) is True
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []
        # The secret itself is untouched — detaching a reference is not a delete.
        remaining = await session.execute(sa.select(LLCSecret.id).where(LLCSecret.id == secret_id))
        assert remaining.scalar_one_or_none() == secret_id
