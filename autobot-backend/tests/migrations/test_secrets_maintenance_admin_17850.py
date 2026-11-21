# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The maintenance admin check reads the STORED admin role, never a caller's claim (#17850), on a real database.

Nothing is mocked: the real ``UserService`` permission lookup runs against migration-built tables. In every refused
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
from services.secrets_principal_resolver import ADMIN_PERMISSION
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ADMIN, _PLAIN, _MISSING, _DELETED = (uuid.uuid4() for _ in range(4))
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
    """An admin (a system role granting the admin permission), a plain user, and a deleted admin."""
    from user_management.models.role import Permission, Role, RolePermission, UserRole
    from user_management.models.user import User

    role_id, permission_id = uuid.uuid4(), uuid.uuid4()
    for uid, name in ((_ADMIN, "root"), (_PLAIN, "plain"), (_DELETED, "gone")):
        session.add(User(id=uid, email=f"{name}@example.com", username=name))
    session.add(Role(id=role_id, name="admin", is_system=True))
    session.add(Permission(id=permission_id, name=ADMIN_PERMISSION, resource="admin", action="access"))
    await session.flush()
    session.add(RolePermission(role_id=role_id, permission_id=permission_id))
    session.add(UserRole(user_id=_ADMIN, role_id=role_id))
    session.add(UserRole(user_id=_DELETED, role_id=role_id))
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
    "who", [_PLAIN, _MISSING, _DELETED], ids=["non-admin-claiming-admin", "missing-user", "deleted-admin"]
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
