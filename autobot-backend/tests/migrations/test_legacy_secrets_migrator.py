# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the legacy Fernet → envelope migrator (#10088 / Task 3a).

Postgres-backed (migration-gate job): seeds legacy Fernet ``secrets`` rows of
each scope on an ``upgrade head`` schema, runs the migrator, and verifies each
row is now envelope-readable via UnifiedSecretsService with the right owner vault
and grants.
"""

import base64
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from services.legacy_secrets_migrator import migrate_pg_legacy_secrets
from services.unified_secrets_service import UnifiedSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_FERNET = Fernet(Fernet.generate_key())
_OWNER = uuid.uuid4()
_ORG = uuid.uuid4()
_FRIEND = uuid.uuid4()
_TEAM = uuid.uuid4()


def _legacy(scope: str, value: bytes, **kw) -> Secret:
    return Secret(
        id=uuid.uuid4(),
        owner_id=_OWNER,
        name=f"{scope}-secret",
        type="password",
        scope=scope,
        encrypted_value=_FERNET.encrypt(value).decode("utf-8"),
        sealed_value=None,
        **kw,
    )


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_migrates_each_scope_and_envelope_readable(session):
    rows = {
        "user": _legacy("user", b"u-val"),
        "organization": _legacy("organization", b"o-val", org_id=_ORG),
        "shared": _legacy("shared", b"s-val", shared_with=[str(_FRIEND)]),
        "group": _legacy("group", b"g-val", team_ids=[str(_TEAM)]),
    }
    for r in rows.values():
        session.add(r)
    await session.commit()

    report = await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.total_legacy == 4 and report.migrated == 4 and report.failed == []

    svc = UnifiedSecretsService(root_key=_ROOT)

    # user → readable via the owner's user vault
    assert (
        await svc.read(session, secret_id=rows["user"].id, accessible_vaults={VaultRef(VaultKind.USER, str(_OWNER))})
        == b"u-val"
    )
    # organization → owned by the company vault
    assert rows["organization"].owner_vault == f"company:{_ORG}"
    assert (
        await svc.read(
            session, secret_id=rows["organization"].id, accessible_vaults={VaultRef(VaultKind.COMPANY, str(_ORG))}
        )
        == b"o-val"
    )
    # shared → owner reads, and the friend reads via their own user vault
    assert (
        await svc.read(session, secret_id=rows["shared"].id, accessible_vaults={VaultRef(VaultKind.USER, str(_FRIEND))})
        == b"s-val"
    )
    assert (
        await svc.read(session, secret_id=rows["shared"].id, accessible_vaults={VaultRef(VaultKind.USER, str(_OWNER))})
        == b"s-val"
    )
    # group → owner reads, and the team vault reads
    assert (
        await svc.read(session, secret_id=rows["group"].id, accessible_vaults={VaultRef(VaultKind.TEAM, str(_TEAM))})
        == b"g-val"
    )


async def test_keeps_legacy_blob_for_rollback(session):
    row = _legacy("user", b"keepme")
    session.add(row)
    await session.commit()
    await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert row.sealed_value is not None
    assert row.encrypted_value is not None  # retained for rollback


async def test_idempotent(session):
    session.add(_legacy("user", b"once"))
    await session.commit()
    first = await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    second = await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    assert first.migrated == 1
    assert second.total_legacy == 0 and second.migrated == 0  # already converted → skipped


async def test_bad_ciphertext_reported_not_raised(session):
    row = Secret(
        id=uuid.uuid4(),
        owner_id=_OWNER,
        name="bad",
        type="password",
        scope="user",
        encrypted_value="not-a-valid-fernet-token",
        sealed_value=None,
    )
    session.add(row)
    await session.commit()
    report = await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    assert report.total_legacy == 1 and report.migrated == 0 and len(report.failed) == 1
    assert row.sealed_value is None  # untouched on failure


async def test_atomic_on_bad_grant_vault(session):
    # A corrupt team id (contains ':') makes grant-building raise mid-row; the seal
    # already succeeded, so this proves the row is left fully untouched (atomic).
    row = _legacy("group", b"g-val", team_ids=["bad:id"])
    session.add(row)
    await session.commit()
    report = await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.total_legacy == 1 and report.migrated == 0 and len(report.failed) == 1
    assert row.sealed_value is None and row.owner_vault is None  # nothing persisted


async def test_org_without_org_id_demoted_with_warning(session):
    # An organization secret missing org_id is migrated to the creator's user vault,
    # and the demotion is surfaced in the report for operator reconciliation.
    row = _legacy("organization", b"o-val")  # no org_id
    session.add(row)
    await session.commit()
    report = await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.migrated == 1 and len(report.warnings) == 1
    assert row.owner_vault == f"user:{_OWNER}"
    svc = UnifiedSecretsService(root_key=_ROOT)
    assert (
        await svc.read(session, secret_id=row.id, accessible_vaults={VaultRef(VaultKind.USER, str(_OWNER))}) == b"o-val"
    )


async def test_dirty_non_list_shared_with_fails_row(session):
    # Legacy dirty data: shared_with stored as a bare string would iterate characters and
    # silently mis-grant — instead the row must fail and be left untouched.
    row = _legacy("shared", b"s-val")
    row.shared_with = "not-a-list"
    session.add(row)
    await session.commit()
    report = await migrate_pg_legacy_secrets(session, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.migrated == 0 and len(report.failed) == 1
    assert row.sealed_value is None
