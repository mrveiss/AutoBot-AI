# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An envelope secret left behind by a deleted user is repaired through its own vault grants (#15779, #16927).

Postgres-backed (migration-gate CI job), against the real ``EnvelopeSecretsService``:
access to an envelope secret is holding a grant for one of your vaults, so "the new
owner can reach it" is proven by ``read()`` and ``list_for_vaults()`` through their
vault -- the real access check. The repair re-wraps the data key; the plaintext never
reaches the result or the audit.
"""

import asyncio
import base64
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.envelope_secrets_service import EnvelopeSecretsService, SecretAccessError
from services.orphan_repair import NotAnOrphan, repair_orphan
from services.orphan_repair_types import EnvelopeSecretRepairer
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_GONE, _NEW, _LIVE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
_PLAINTEXT = b"orphan-repair-plaintext-must-not-leak"


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        from user_management.models.user import User

        for uid, name in ((_GONE, "gone"), (_NEW, "heir"), (_LIVE, "live")):
            s.add(User(id=uid, email=f"{name}@example.com", username=name))
        await s.flush()
        (await s.get(User, _GONE)).deleted_at = datetime.now(tz=timezone.utc)  # soft-deleted
        await s.commit()
        yield s
    await engine.dispose()


@pytest.fixture()
def service():
    return EnvelopeSecretsService(root_key=_ROOT)


async def _secret_owned_by(service, session, owner):
    vault = VaultRef(VaultKind.USER, str(owner))
    secret = await service.create(
        session, owner_vault=vault, name="k", secret_type="api_key", plaintext=_PLAINTEXT, created_by=owner
    )
    await session.commit()
    return secret.id


def _repairers(service):
    return {"secret": EnvelopeSecretRepairer(service_factory=lambda: service)}


async def test_a_deleted_users_secret_is_repaired_and_the_new_owner_reads_it(session, service):
    secret_id = await _secret_owned_by(service, session, _GONE)
    new_vault = VaultRef(VaultKind.USER, str(_NEW))
    with pytest.raises(SecretAccessError):
        await service.read(session, secret_id=secret_id, accessible_vaults={new_vault})

    with patch("services.orphan_repair.audit_log", new=AsyncMock(return_value=True)) as audit:
        result = await repair_orphan(
            session, _repairers(service), "secret", str(secret_id), str(_NEW), actor_user_id="admin"
        )

    assert await service.read(session, secret_id=secret_id, accessible_vaults={new_vault}) == _PLAINTEXT
    assert secret_id in {s.id for s in await service.list_for_vaults(session, accessible_vaults={new_vault})}
    assert result["conditions"]["dead_vaults"] == [f"user:{_GONE}"]
    assert result["after"]["owner_vault"] == new_vault.to_str()
    leaked = _PLAINTEXT.decode()
    assert leaked not in repr(result) and leaked not in repr(audit.await_args), "the plaintext must never leave"


async def test_the_negative_control_a_live_users_secret_is_refused(session, service):
    secret_id = await _secret_owned_by(service, session, _LIVE)

    with patch("services.orphan_repair.audit_log", new=AsyncMock(return_value=True)):
        with pytest.raises(NotAnOrphan):
            await repair_orphan(session, _repairers(service), "secret", str(secret_id), str(_NEW), actor_user_id="a")

    with pytest.raises(SecretAccessError):
        await service.read(session, secret_id=secret_id, accessible_vaults={VaultRef(VaultKind.USER, str(_NEW))})


async def test_a_secret_a_live_vault_also_holds_is_refused(session, service):
    secret_id = await _secret_owned_by(service, session, _GONE)
    await service.share(
        session,
        secret_id=secret_id,
        actor_vaults={VaultRef(VaultKind.USER, str(_GONE))},
        grantee=VaultRef(VaultKind.USER, str(_LIVE)),
        created_by=_LIVE,
    )
    await session.commit()

    with patch("services.orphan_repair.audit_log", new=AsyncMock(return_value=True)):
        with pytest.raises(NotAnOrphan):
            await repair_orphan(session, _repairers(service), "secret", str(secret_id), str(_NEW), actor_user_id="a")


async def test_two_concurrent_repairs_serialize_and_the_second_finds_a_live_owner(session, service, fresh_db_url):
    """The judgment holds at the write: the secret row stays locked from assess to commit."""
    secret_id = await _secret_owned_by(service, session, _GONE)
    engine = create_async_engine(fresh_db_url)
    other = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        with patch("services.orphan_repair.audit_log", new=AsyncMock(return_value=True)):
            await repair_orphan(session, _repairers(service), "secret", str(secret_id), str(_NEW), actor_user_id="a")
            second = asyncio.create_task(
                repair_orphan(other, _repairers(service), "secret", str(secret_id), str(_LIVE), actor_user_id="b")
            )
            await asyncio.sleep(0.5)
            assert not second.done(), "the second repair must wait on the first's row lock"
            await session.commit()
            with pytest.raises(NotAnOrphan):
                await second
    finally:
        await other.close()
        await engine.dispose()
