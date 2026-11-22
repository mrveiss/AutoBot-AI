# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The maintenance admin check reads the STORED admin role, never a caller's claim (#17850), on a real database.

Nothing is mocked: the real user row is loaded from migration-built tables and judged by ``is_admin_role``.
In every refused
case nothing is audited and nothing is opened or deleted.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services import secrets_maintenance as maintenance
from services.envelope_secrets_service import SecretAccessError
from services.secrets_coordinator import SecretsCoordinator
from services.secrets_maintenance import MaintenanceActor
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ADMIN, _PLAIN, _MISSING, _DELETED, _INACTIVE = (uuid.uuid4() for _ in range(5))
_SECRET = uuid.uuid4()


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
    """An admin (``is_platform_admin``, the flag login turns into the admin role), a plain user, a deleted admin and
    an inactive admin."""
    from user_management.models.user import User

    for uid, name, admin in ((_ADMIN, "root", True), (_PLAIN, "plain", False), (_DELETED, "gone", True)):
        session.add(User(id=uid, email=f"{name}@example.com", username=name, is_platform_admin=admin))
    session.add(User(id=_INACTIVE, email="idle@example.com", username="idle", is_platform_admin=True, is_active=False))
    await session.flush()
    (await session.get(User, _DELETED)).soft_delete()
    await session.commit()


def _coordinator(monkeypatch):
    service = MagicMock(read=AsyncMock(return_value=b"v"), delete=AsyncMock())
    coordinator = SecretsCoordinator(service)
    audit = AsyncMock(return_value=True)
    monkeypatch.setattr(maintenance, "audit_log", audit)
    monkeypatch.setattr(coordinator, "_owner_vault", AsyncMock(return_value=MagicMock()))
    return coordinator, service, audit


@pytest.mark.parametrize(
    "who",
    [_PLAIN, _MISSING, _DELETED, _INACTIVE],
    ids=["non-admin-claiming-admin", "missing-user", "deleted-admin", "inactive-admin"],
)
async def test_a_refused_actor_opens_nothing_deletes_nothing_and_audits_nothing(session, monkeypatch, who):
    coordinator, service, audit = _coordinator(monkeypatch)
    actor = MaintenanceActor(who, "ref")
    with pytest.raises(SecretAccessError):
        await coordinator.maintenance_read(session, actor=actor, secret_id=_SECRET)
    with pytest.raises(SecretAccessError):
        await coordinator.maintenance_delete(session, actor=actor, secret_id=_SECRET)
    service.read.assert_not_called()
    service.delete.assert_not_called()
    audit.assert_not_called()


async def test_a_stored_administrator_passes_and_is_audited_first(session, monkeypatch):
    coordinator, service, audit = _coordinator(monkeypatch)
    value = await coordinator.maintenance_read(session, actor=MaintenanceActor(_ADMIN, "ref"), secret_id=_SECRET)
    assert value == b"v"
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["user_id"] == str(_ADMIN)
    service.read.assert_awaited_once()


def test_an_actor_carries_no_permissions_a_caller_could_claim():
    assert not hasattr(MaintenanceActor(_ADMIN, "ref"), "permissions")
