# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the PrincipalFacts DB resolver (#10088 / Task 2.3 part 2).

Postgres-backed (co-located under tests/migrations for the migration-gate CI
job): builds the full schema via ``alembic upgrade head`` so the membership
FKs resolve, seeds one user with a team / role / company membership, and
asserts the resolver reads them into PrincipalFacts.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llc.models.enums import MembershipRole
from services.secrets_principal_resolver import resolve_principal_facts
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_USER = uuid.uuid4()
_COMPANY = uuid.uuid4()


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await _seed(s)
        yield s
    await engine.dispose()


async def _seed(session) -> None:
    """One user holding a role and an LLC company membership.

    The team path (organizations → teams → team_memberships) is not seeded here:
    the ``organizations`` ORM model has columns no migration adds (#10189), so an
    ORM Organization insert fails on a migration-built DB. The team query is
    structurally identical to the role query (both join through a membership
    table) and is covered by the empty-result assertion; the positive team path
    rides 2.4's end-to-end test once #10189 is fixed.
    """
    from llc.models.membership import LLCCompanyMembership
    from user_management.models.role import Role, UserRole
    from user_management.models.user import User

    role_id = uuid.uuid4()
    session.add(User(id=_USER, email="alice@example.com", username="alice"))
    session.add(Role(id=role_id, name="engineer"))
    await session.flush()
    session.add(UserRole(user_id=_USER, role_id=role_id))
    session.add(LLCCompanyMembership(company_id=_COMPANY, user_id=_USER, role="admin"))
    await session.commit()
    session.expunge_all()


async def test_resolves_role_and_company_memberships(session):
    facts = await resolve_principal_facts(session, _USER, {"secrets:system:read", "other:x"})
    assert facts.user_id == str(_USER)
    assert facts.role_names == frozenset({"engineer"})
    assert facts.company_roles == {str(_COMPANY): MembershipRole.ADMIN}
    assert facts.team_ids == frozenset()  # no team seeded; query returns empty cleanly
    # only secrets:* permissions are retained as granted
    assert facts.granted_permissions == frozenset({"secrets:system:read"})
    assert facts.is_admin is False


async def test_admin_permission_sets_is_admin(session):
    facts = await resolve_principal_facts(session, _USER, {"admin:access"})
    assert facts.is_admin is True


async def test_unknown_user_has_empty_memberships(session):
    # An absent user_id (a non-User principal) keeps permission-only behaviour, stays active.
    facts = await resolve_principal_facts(session, uuid.uuid4(), {"secrets:user:read"})
    assert facts.active is True
    assert facts.team_ids == frozenset()
    assert facts.role_names == frozenset()
    assert facts.company_roles == {}
    assert facts.granted_permissions == frozenset({"secrets:user:read"})


async def test_deactivated_user_reaches_no_vault(session):
    # A soft-deleted/deactivated user (exists, is_active=False) gets inactive facts → no access,
    # even holding admin permission (residual access from a still-valid session is denied). #10346
    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from services.secrets_authz import authorize
    from user_management.models.user import User

    dead = uuid.uuid4()
    session.add(User(id=dead, email="dead@example.com", username="dead", is_active=False))
    await session.commit()

    facts = await resolve_principal_facts(session, dead, {"admin:access"})
    assert facts.active is False
    assert facts.accessible_vaults() == set()  # not even their own user vault
    assert authorize(facts, "read", VaultRef(VaultKind.USER, str(dead))) is False
    assert authorize(facts, "read", VaultRef(VaultKind.SYSTEM)) is False


async def test_accessible_vaults_compose_from_resolved_facts(session):
    from autobot_shared.secrets_vault import VaultKind, VaultRef

    facts = await resolve_principal_facts(session, _USER, set())
    vaults = facts.accessible_vaults()
    assert VaultRef(VaultKind.USER, str(_USER)) in vaults
    assert VaultRef(VaultKind.COMPANY, str(_COMPANY)) in vaults
    assert VaultRef(VaultKind.ROLE, "engineer") in vaults
