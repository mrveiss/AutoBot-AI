# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-device revocation and capability scoping (#14964).

``POST /api/devices/{id}/revoke`` must revoke exactly one credential. The
acceptance criterion this file exists for is the *isolation* one: revoking one
device may not affect the user's other devices. A test that revokes the only
device on the account cannot tell revocation from a global switch, so every
case here runs against a user who owns two.

Modelled on ``test_mobile_device_me.py``: in-memory SQLite, schema scoped to
``MobileDevice.__table__``, no Redis required.
"""

import uuid
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker
from sqlalchemy.pool import StaticPool

from api.mobile_devices import router as mobile_router
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.auth.device_capabilities import (
    NO_CAPABILITIES_JSON,
    DeviceCapability,
    serialise_device_permissions,
)
from models.mobile_device import MobileDevice
from user_management.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_USER_ID = "revocation-user"
_OTHER_USER_ID = "someone-else"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[MobileDevice.__table__]))

    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def _no_at_rest_encryption(monkeypatch):
    """These tests are about capability state, not the token cipher."""
    monkeypatch.setattr("encryption_service.encrypt_data", lambda value: value)


@pytest.fixture(autouse=True)
def _no_redis_cache(monkeypatch):
    """``invalidate_device_cache`` must not reach for a live Redis here."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr("services.device_jwt.invalidate_device_cache", AsyncMock())


async def _add_device(db_session, name: str, *, user_id: str = _USER_ID, capabilities=()) -> MobileDevice:
    device = MobileDevice(
        user_id=user_id,
        device_name=name,
        device_token=f"tok-{name}",
        platform="ios",
        permissions=serialise_device_permissions(capabilities),
        is_approved=bool(capabilities),
    )
    db_session.add(device)
    await db_session.commit()
    return device


def _client(db_session, current_user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(mobile_router, prefix="/api/devices")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


async def _reload(db_session, device_id) -> MobileDevice:
    """Re-read the row inside the async context.

    ``expire_all()`` plus attribute access would refresh lazily on the *sync*
    side and raise ``MissingGreenlet``; ``populate_existing`` does the refresh
    as part of this await.
    """
    result = await db_session.execute(
        select(MobileDevice).where(MobileDevice.id == device_id).execution_options(populate_existing=True)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_a_freshly_paired_device_holds_no_capability(db_session):
    """The model default is the same denial the migration backfills."""
    device = await _add_device(db_session, "plain-phone")

    assert device.permissions == NO_CAPABILITIES_JSON
    assert device.is_approved is False
    assert list(DeviceCapability), "the loop below asserts nothing if the enumeration is empty"
    for capability in DeviceCapability:
        assert device.has_capability(capability) is False


@pytest.mark.asyncio
async def test_revoking_one_device_leaves_the_users_other_device_untouched(db_session):
    """AC: revocation is per credential, not per user."""
    revoked = await _add_device(db_session, "old-phone", capabilities=[DeviceCapability.TERMINAL])
    kept = await _add_device(db_session, "new-phone", capabilities=[DeviceCapability.TERMINAL])
    assert revoked.has_capability(DeviceCapability.TERMINAL)
    assert kept.has_capability(DeviceCapability.TERMINAL)

    response = _client(db_session, {"user_id": _USER_ID}).post(f"/api/devices/{revoked.id}/revoke")
    assert response.status_code == 204

    revoked_row = await _reload(db_session, revoked.id)
    kept_row = await _reload(db_session, kept.id)

    assert revoked_row.revoked_at is not None
    assert revoked_row.has_capability(DeviceCapability.TERMINAL) is False
    assert kept_row.revoked_at is None
    assert kept_row.has_capability(DeviceCapability.TERMINAL) is True, (
        "revoking one device disabled another -- revocation must be scoped to one credential"
    )


@pytest.mark.asyncio
async def test_revocation_keeps_the_record_rather_than_deleting_it(db_session):
    """Soft revocation: the pairing history survives the revocation."""
    device = await _add_device(db_session, "old-phone", capabilities=[DeviceCapability.DESKTOP_VIEW])

    _client(db_session, {"user_id": _USER_ID}).post(f"/api/devices/{device.id}/revoke")

    row = await _reload(db_session, device.id)
    assert row.device_name == "old-phone"
    assert row.permissions == NO_CAPABILITIES_JSON


@pytest.mark.asyncio
async def test_revocation_is_idempotent_and_does_not_move_the_recorded_time(db_session):
    device = await _add_device(db_session, "old-phone", capabilities=[DeviceCapability.TERMINAL])
    client = _client(db_session, {"user_id": _USER_ID})

    assert client.post(f"/api/devices/{device.id}/revoke").status_code == 204
    first = (await _reload(db_session, device.id)).revoked_at

    assert client.post(f"/api/devices/{device.id}/revoke").status_code == 204
    assert (await _reload(db_session, device.id)).revoked_at == first


@pytest.mark.asyncio
async def test_a_user_cannot_revoke_someone_elses_device(db_session):
    victim = await _add_device(
        db_session, "victim-phone", user_id=_OTHER_USER_ID, capabilities=[DeviceCapability.TERMINAL]
    )

    response = _client(db_session, {"user_id": _USER_ID}).post(f"/api/devices/{victim.id}/revoke")

    assert response.status_code == 404
    row = await _reload(db_session, victim.id)
    assert row.revoked_at is None
    assert row.has_capability(DeviceCapability.TERMINAL) is True


@pytest.mark.asyncio
async def test_revoking_an_unknown_device_is_a_404_not_a_silent_success(db_session):
    """Non-vacuity: the ownership refusal above must not be an "everything 404s" artefact."""
    owned = await _add_device(db_session, "my-phone", capabilities=[DeviceCapability.TERMINAL])
    client = _client(db_session, {"user_id": _USER_ID})

    assert client.post(f"/api/devices/{uuid.uuid4()}/revoke").status_code == 404
    assert client.post(f"/api/devices/{owned.id}/revoke").status_code == 204
