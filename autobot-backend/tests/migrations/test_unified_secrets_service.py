# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end tests for UnifiedSecretsService (#10088 / Task 2.2).

Co-located under tests/migrations because that is AutoBot's Postgres-backed CI
job (migration-gate): the service stores JSONB + Uuid columns, so it needs a
real Postgres, not SQLite. Builds just the ``secrets`` + ``secret_grants``
tables (no FKs out of them) and exercises create/read/share/revoke/rotate.
"""

import base64
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from models.secret_grant import SecretGrant
from services.unified_secrets_service import (
    SecretAccessError,
    SecretNotFoundError,
    UnifiedSecretsService,
)
from tests.migrations.conftest import requires_postgres

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_USER = VaultRef(VaultKind.USER, "alice")
_COMPANY = VaultRef(VaultKind.COMPANY, "acme")
_OTHER = VaultRef(VaultKind.COMPANY, "rival")


@pytest.fixture()
async def session(fresh_db_url):
    engine = create_async_engine(fresh_db_url)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Secret.__table__.create(c))
        await conn.run_sync(lambda c: SecretGrant.__table__.create(c))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture()
def svc():
    return UnifiedSecretsService(root_key=_ROOT)


async def _new(svc, session, **kw):
    defaults = dict(owner_vault=_USER, name="api", secret_type="api_key", plaintext=b"s3cr3t", created_by=uuid.uuid4())
    defaults.update(kw)
    secret = await svc.create(session, **defaults)
    await session.commit()
    return secret


async def test_create_then_read_by_owner(svc, session):
    secret = await _new(svc, session)
    assert await svc.read(session, secret_id=secret.id, accessible_vaults={_USER}) == b"s3cr3t"
    assert secret.sealed_value is not None and secret.encrypted_value is None
    assert secret.owner_vault == "user:alice" and secret.version == 1


async def test_read_without_access_denied(svc, session):
    secret = await _new(svc, session)
    with pytest.raises(SecretAccessError):
        await svc.read(session, secret_id=secret.id, accessible_vaults={_OTHER})


async def test_share_then_read_by_grantee(svc, session):
    secret = await _new(svc, session)
    await svc.share(session, secret_id=secret.id, actor_vaults={_USER}, grantee=_COMPANY, created_by=uuid.uuid4())
    await session.commit()
    assert await svc.read(session, secret_id=secret.id, accessible_vaults={_COMPANY}) == b"s3cr3t"
    # owner still reads too (multi-grantee)
    assert await svc.read(session, secret_id=secret.id, accessible_vaults={_USER}) == b"s3cr3t"


async def test_share_is_idempotent_rewrap(svc, session):
    secret = await _new(svc, session)
    await svc.share(session, secret_id=secret.id, actor_vaults={_USER}, grantee=_COMPANY, created_by=uuid.uuid4())
    await svc.share(session, secret_id=secret.id, actor_vaults={_USER}, grantee=_COMPANY, created_by=uuid.uuid4())
    await session.commit()
    grants = await svc._grants(session, secret.id)
    assert sum(1 for g in grants if g.grantee == "company:acme") == 1  # no duplicate row


async def test_revoke_removes_access(svc, session):
    secret = await _new(svc, session)
    await svc.share(session, secret_id=secret.id, actor_vaults={_USER}, grantee=_COMPANY, created_by=uuid.uuid4())
    await session.commit()
    await svc.revoke(session, secret_id=secret.id, grantee=_COMPANY)
    await session.commit()
    with pytest.raises(SecretAccessError):
        await svc.read(session, secret_id=secret.id, accessible_vaults={_COMPANY})
    assert await svc.read(session, secret_id=secret.id, accessible_vaults={_USER}) == b"s3cr3t"


async def test_cannot_revoke_owner_grant(svc, session):
    secret = await _new(svc, session)
    with pytest.raises(ValueError, match="owner grant"):
        await svc.revoke(session, secret_id=secret.id, grantee=_USER)


async def test_rotate_value_rewraps_all_grantees(svc, session):
    secret = await _new(svc, session)
    await svc.share(session, secret_id=secret.id, actor_vaults={_USER}, grantee=_COMPANY, created_by=uuid.uuid4())
    await session.commit()
    await svc.rotate_value(session, secret_id=secret.id, new_plaintext=b"rotated", actor_vaults={_USER})
    await session.commit()
    assert secret.version == 2
    # both grantees read the NEW value
    assert await svc.read(session, secret_id=secret.id, accessible_vaults={_USER}) == b"rotated"
    assert await svc.read(session, secret_id=secret.id, accessible_vaults={_COMPANY}) == b"rotated"


async def test_rotate_requires_access(svc, session):
    secret = await _new(svc, session)
    with pytest.raises(SecretAccessError):
        await svc.rotate_value(session, secret_id=secret.id, new_plaintext=b"x", actor_vaults={_OTHER})


async def test_list_for_vaults(svc, session):
    s1 = await _new(svc, session, name="one")
    await _new(svc, session, name="two", owner_vault=_COMPANY)
    got = await svc.list_for_vaults(session, accessible_vaults={_USER})
    assert [s.id for s in got] == [s1.id]
    assert await svc.list_for_vaults(session, accessible_vaults={_OTHER}) == []


async def test_delete_cascades_grants(svc, session):
    secret = await _new(svc, session)
    await svc.delete(session, secret_id=secret.id)
    await session.commit()
    with pytest.raises(SecretNotFoundError):
        await svc.read(session, secret_id=secret.id, accessible_vaults={_USER})
    assert await svc._grants(session, secret.id) == []


async def test_read_missing_secret(svc, session):
    with pytest.raises(SecretNotFoundError):
        await svc.read(session, secret_id=uuid.uuid4(), accessible_vaults={_USER})
