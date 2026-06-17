# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end tests for SecretsCoordinator (#10088 / Task 2.4).

Postgres-backed (migration-gate CI job): builds the full schema via
``alembic upgrade head`` (so ``secrets``/``secret_grants``/``llc_company_memberships``
all exist), seeds a company-admin user, and exercises the resolve→authorize→
service path for create/read/share/revoke/rotate/delete plus denial cases.
"""

import base64
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.secrets_coordinator import SecretsCoordinator
from services.unified_secrets_service import SecretAccessError, SecretNotFoundError, UnifiedSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_ADMIN = uuid.uuid4()  # company admin
_OUTSIDER = uuid.uuid4()  # no memberships
_GRANTEE_USER = uuid.uuid4()
_COMPANY = uuid.uuid4()
_COMPANY_VAULT = VaultRef(VaultKind.COMPANY, str(_COMPANY))
_NO_PERMS: set[str] = set()


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        from llc.models.membership import LLCCompanyMembership
        from user_management.models.user import User

        for uid, uname in ((_ADMIN, "admin"), (_OUTSIDER, "outsider"), (_GRANTEE_USER, "grantee")):
            s.add(User(id=uid, email=f"{uname}@example.com", username=uname))
        s.add(LLCCompanyMembership(company_id=_COMPANY, user_id=_ADMIN, role="admin"))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.fixture()
def coord():
    return SecretsCoordinator(UnifiedSecretsService(root_key=_ROOT))


async def _make(coord, session) -> uuid.UUID:
    secret = await coord.create(
        session,
        user_id=_ADMIN,
        permissions=_NO_PERMS,
        owner_vault=_COMPANY_VAULT,
        name="db",
        secret_type="password",
        plaintext=b"hunter2",
    )
    await session.commit()
    return secret.id


async def test_company_admin_create_and_read(coord, session):
    sid = await _make(coord, session)
    assert await coord.read(session, user_id=_ADMIN, permissions=_NO_PERMS, secret_id=sid) == b"hunter2"


async def test_outsider_cannot_create(coord, session):
    with pytest.raises(SecretAccessError):
        await coord.create(
            session,
            user_id=_OUTSIDER,
            permissions=_NO_PERMS,
            owner_vault=_COMPANY_VAULT,
            name="x",
            secret_type="password",
            plaintext=b"x",
        )


async def test_outsider_cannot_read(coord, session):
    sid = await _make(coord, session)
    with pytest.raises(SecretAccessError):
        await coord.read(session, user_id=_OUTSIDER, permissions=_NO_PERMS, secret_id=sid)


async def test_share_to_user_then_grantee_reads(coord, session):
    sid = await _make(coord, session)
    await coord.share(
        session,
        user_id=_ADMIN,
        permissions=_NO_PERMS,
        secret_id=sid,
        grantee=VaultRef(VaultKind.USER, str(_GRANTEE_USER)),
    )
    await session.commit()
    # the grantee opens it via their own user vault, with no company membership
    assert await coord.read(session, user_id=_GRANTEE_USER, permissions=_NO_PERMS, secret_id=sid) == b"hunter2"


async def test_outsider_cannot_share(coord, session):
    sid = await _make(coord, session)
    with pytest.raises(SecretAccessError):
        await coord.share(
            session,
            user_id=_OUTSIDER,
            permissions=_NO_PERMS,
            secret_id=sid,
            grantee=VaultRef(VaultKind.USER, str(_OUTSIDER)),
        )


async def test_revoke_then_grantee_denied(coord, session):
    sid = await _make(coord, session)
    grantee = VaultRef(VaultKind.USER, str(_GRANTEE_USER))
    await coord.share(session, user_id=_ADMIN, permissions=_NO_PERMS, secret_id=sid, grantee=grantee)
    await session.commit()
    await coord.revoke(session, user_id=_ADMIN, permissions=_NO_PERMS, secret_id=sid, grantee=grantee)
    await session.commit()
    with pytest.raises(SecretAccessError):
        await coord.read(session, user_id=_GRANTEE_USER, permissions=_NO_PERMS, secret_id=sid)


async def test_rotate_and_list(coord, session):
    sid = await _make(coord, session)
    await coord.rotate(session, user_id=_ADMIN, permissions=_NO_PERMS, secret_id=sid, new_plaintext=b"rotated")
    await session.commit()
    assert await coord.read(session, user_id=_ADMIN, permissions=_NO_PERMS, secret_id=sid) == b"rotated"
    listed = await coord.list(session, user_id=_ADMIN, permissions=_NO_PERMS)
    assert [s.id for s in listed] == [sid]
    assert await coord.list(session, user_id=_OUTSIDER, permissions=_NO_PERMS) == []


async def test_delete_then_not_found(coord, session):
    sid = await _make(coord, session)
    await coord.delete(session, user_id=_ADMIN, permissions=_NO_PERMS, secret_id=sid)
    await session.commit()
    with pytest.raises(SecretNotFoundError):
        await coord.read(session, user_id=_ADMIN, permissions=_NO_PERMS, secret_id=sid)


async def test_mutation_on_missing_secret_raises_not_found(coord, session):
    with pytest.raises(SecretNotFoundError):
        await coord.share(
            session,
            user_id=_ADMIN,
            permissions=_NO_PERMS,
            secret_id=uuid.uuid4(),
            grantee=VaultRef(VaultKind.USER, str(_GRANTEE_USER)),
        )
