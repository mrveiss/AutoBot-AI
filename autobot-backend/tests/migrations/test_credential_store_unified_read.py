# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Postgres core test for the ConnectorCredentialStore unified read (#10088 / Task 3c-2).

Seeds an imported-style envelope secret (carrying the ``imported_from_sqlite`` marker)
and verifies the unified-read core resolves it by legacy id, decrypts via the owner's
user vault, and falls back (returns None) when not imported or not accessible.
"""

import base64
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from knowledge.connectors.credential_store import _read_unified_in_session
from services.unified_secrets_service import UnifiedSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_OWNER = uuid.uuid4()


@pytest.fixture()
async def session(fresh_db_url, monkeypatch):
    # _read_unified_in_session builds UnifiedSecretsService() which reads the root key from env.
    monkeypatch.setenv("AUTOBOT_SECRETS_ROOT_KEY", base64.urlsafe_b64encode(_ROOT).decode("utf-8"))
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed(session, legacy_id: str, value: bytes, owner=_OWNER):
    svc = UnifiedSecretsService(root_key=_ROOT)
    secret = await svc.create(
        session,
        owner_vault=VaultRef(VaultKind.USER, str(owner)),
        name="connector:x:auth",
        secret_type="connector_oauth_token",
        plaintext=value,
        created_by=owner,
    )
    secret.extra_data = {"imported_from_sqlite": legacy_id}
    await session.flush()
    return secret


async def test_reads_imported_by_marker(session):
    await _seed(session, "legacy-1", b'{"token":"abc"}')
    await session.commit()
    out = await _read_unified_in_session(session, "legacy-1", str(_OWNER))
    assert out == {"created_by": str(_OWNER), "value": '{"token":"abc"}'}


async def test_returns_none_when_not_imported(session):
    await _seed(session, "legacy-1", b'{"token":"abc"}')
    await session.commit()
    assert await _read_unified_in_session(session, "no-such-id", str(_OWNER)) is None


async def test_returns_none_on_owner_mismatch(session):
    await _seed(session, "legacy-1", b'{"token":"abc"}')
    await session.commit()
    # A different owner has no grant → SecretAccessError caught → fall back to SQLite.
    assert await _read_unified_in_session(session, "legacy-1", str(uuid.uuid4())) is None
