# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for secrets access-transparency — "who can access this secret" (#10088 / Task 4).

Postgres-backed (migration-gate): seeds a user-, role-, and company-scoped membership graph,
shares one secret to those vaults, and asserts the audit resolves each grantee vault to its
member users. (The team path needs an Organization → not seeded here, same as the resolver
test; its query is structurally identical to the role path.)
"""

import base64
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.secrets_access_audit import describe_secret_access
from services.unified_secrets_service import UnifiedSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_OWNER = uuid.uuid4()  # owner (user vault); not seeded as a User row — audit returns the id as-is
_ALICE = uuid.uuid4()  # role member
_BOB = uuid.uuid4()  # company member
_COMPANY = uuid.uuid4()


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed_memberships(session) -> None:
    from llc.models.membership import LLCCompanyMembership
    from user_management.models.role import Role, UserRole
    from user_management.models.user import User

    role_id = uuid.uuid4()
    session.add(User(id=_ALICE, email="alice@example.com", username="alice"))
    session.add(User(id=_BOB, email="bob@example.com", username="bob"))
    session.add(Role(id=role_id, name="engineer"))
    await session.flush()
    session.add(UserRole(user_id=_ALICE, role_id=role_id))
    session.add(LLCCompanyMembership(company_id=_COMPANY, user_id=_BOB, role="member"))
    await session.flush()


async def test_describe_resolves_grantee_members(session):
    await _seed_memberships(session)
    svc = UnifiedSecretsService(root_key=_ROOT)
    owner = VaultRef(VaultKind.USER, str(_OWNER))
    secret = await svc.create(
        session, owner_vault=owner, name="db-pw", secret_type="password", plaintext=b"v", created_by=_OWNER
    )
    await svc.share(
        session,
        secret_id=secret.id,
        actor_vaults={owner},
        grantee=VaultRef(VaultKind.ROLE, "engineer"),
        created_by=_OWNER,
    )
    await svc.share(
        session,
        secret_id=secret.id,
        actor_vaults={owner},
        grantee=VaultRef(VaultKind.COMPANY, str(_COMPANY)),
        created_by=_OWNER,
    )
    await session.commit()

    report = await describe_secret_access(session, secret.id)
    assert report is not None
    assert report.owner_vault == f"user:{_OWNER}"
    by_vault = {g.vault: g for g in report.grants}
    assert by_vault[f"user:{_OWNER}"].members == [str(_OWNER)]  # owner grant → the owner
    assert by_vault["role:engineer"].members == [str(_ALICE)]  # role → its member
    assert by_vault[f"company:{_COMPANY}"].members == [str(_BOB)]  # company → its member
    assert report.effective_users == sorted({str(_OWNER), str(_ALICE), str(_BOB)})


async def test_describe_missing_secret_returns_none(session):
    assert await describe_secret_access(session, uuid.uuid4()) is None


async def test_audit_excludes_inactive_members(session):
    # A deactivated user in a granted role must not be listed as having access (#10346); unknown
    # ids (the owner here, not seeded as a User row) are kept.
    from user_management.models.role import Role, UserRole
    from user_management.models.user import User

    dead = uuid.uuid4()
    role_id = uuid.uuid4()
    session.add(User(id=dead, email="dead@example.com", username="dead", is_active=False))
    session.add(Role(id=role_id, name="ops"))
    await session.flush()
    session.add(UserRole(user_id=dead, role_id=role_id))

    svc = UnifiedSecretsService(root_key=_ROOT)
    owner = VaultRef(VaultKind.USER, str(_OWNER))
    secret = await svc.create(
        session, owner_vault=owner, name="x", secret_type="password", plaintext=b"v", created_by=_OWNER
    )
    await svc.share(
        session, secret_id=secret.id, actor_vaults={owner}, grantee=VaultRef(VaultKind.ROLE, "ops"), created_by=_OWNER
    )
    await session.commit()

    report = await describe_secret_access(session, secret.id)
    by_vault = {g.vault: g for g in report.grants}
    assert by_vault["role:ops"].members == []  # inactive role member excluded
    assert str(dead) not in report.effective_users
    assert str(_OWNER) in report.effective_users  # owner (unknown id) kept


async def test_describe_unshared_secret_lists_only_owner(session):
    svc = UnifiedSecretsService(root_key=_ROOT)
    owner = VaultRef(VaultKind.USER, str(_OWNER))
    secret = await svc.create(
        session, owner_vault=owner, name="solo", secret_type="password", plaintext=b"v", created_by=_OWNER
    )
    await session.commit()
    report = await describe_secret_access(session, secret.id)
    assert [g.vault for g in report.grants] == [f"user:{_OWNER}"]
    assert report.effective_users == [str(_OWNER)]


async def test_coordinator_authorizes_owner_denies_stranger(session):
    from services.secrets_coordinator import SecretsCoordinator
    from services.unified_secrets_service import SecretAccessError, SecretNotFoundError

    coord = SecretsCoordinator(service=UnifiedSecretsService(root_key=_ROOT))
    owner = VaultRef(VaultKind.USER, str(_OWNER))
    secret = await coord.create(
        session, user_id=_OWNER, permissions=set(), owner_vault=owner, name="x", secret_type="password", plaintext=b"v"
    )
    await session.commit()

    # the owner may view who has access
    report = await coord.describe_access(session, user_id=_OWNER, permissions=set(), secret_id=secret.id)
    assert report.owner_vault == f"user:{_OWNER}"
    # a stranger (non-admin, no grant on the owner vault) may not
    with pytest.raises(SecretAccessError):
        await coord.describe_access(session, user_id=uuid.uuid4(), permissions=set(), secret_id=secret.id)
    # an admin may view any secret's access
    admin_report = await coord.describe_access(
        session, user_id=uuid.uuid4(), permissions={"admin:access"}, secret_id=secret.id
    )
    assert admin_report.secret_id == str(secret.id)
    # missing secret → 404-equivalent
    with pytest.raises(SecretNotFoundError):
        await coord.describe_access(session, user_id=_OWNER, permissions=set(), secret_id=uuid.uuid4())


async def test_company_member_cannot_audit(session):
    # H1: a company MEMBER can read/write company secrets but lacks 'share' authority, so it must
    # NOT be able to enumerate who-has-access. Only OWNER/ADMIN/LEAD (manage authority) or admins may.
    from services.secrets_coordinator import SecretsCoordinator
    from services.unified_secrets_service import SecretAccessError

    await _seed_memberships(session)  # _BOB is a "member" of _COMPANY
    coord = SecretsCoordinator(service=UnifiedSecretsService(root_key=_ROOT))
    company = VaultRef(VaultKind.COMPANY, str(_COMPANY))
    secret = await coord.create(
        session, user_id=_BOB, permissions=set(), owner_vault=company, name="cs", secret_type="password", plaintext=b"v"
    )
    await session.commit()
    with pytest.raises(SecretAccessError):
        await coord.describe_access(session, user_id=_BOB, permissions=set(), secret_id=secret.id)
