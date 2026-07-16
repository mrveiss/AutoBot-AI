# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GET /api/devices/me — require_device_jwt wiring tests (#11736).

Separate from test_mobile_pairing.py on purpose: that module's autouse
Redis-cleanup fixture skips the whole file when Redis is unavailable
(CI included), and these tests need only the in-memory database. Keeping
them here guarantees the #11736 wiring is always exercised.
"""

import uuid
from datetime import timedelta
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker
from sqlalchemy.pool import StaticPool

from api.mobile_devices import _device_jwt_auth
from api.mobile_devices import router as mobile_router
from api.user_management.dependencies import get_db_session
from autobot_shared.time_utils import now_utc
from models.mobile_device import MobileDevice
from user_management.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_USER_ID = "device-me-user"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory database session with the mobile-device schema."""
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def paired_device(db_session, monkeypatch) -> MobileDevice:
    """A paired device whose last_seen_at is 10 days stale."""
    # Token encryption needs AUTOBOT_ENCRYPTION_KEY; these tests only care
    # about identity/heartbeat, so stub the at-rest encryption.
    monkeypatch.setattr("encryption_service.encrypt_data", lambda value: value)
    device = MobileDevice(
        user_id=_USER_ID,
        device_name="Heartbeat Phone",
        device_token="tok-hb",
        platform="ios",
        last_seen_at=now_utc() - timedelta(days=10),
    )
    db_session.add(device)
    await db_session.commit()
    return device


def _client(db_session, device_user: dict) -> TestClient:
    """Client with the DB and device-JWT dependencies overridden."""
    app = FastAPI()
    app.include_router(mobile_router, prefix="/api/devices")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[_device_jwt_auth] = lambda: device_user
    return TestClient(app)


def test_device_me_route_wired_to_require_device_jwt():
    """GET /me is guarded by the module-level require_device_jwt dependency."""
    from api import mobile_devices

    route = next(r for r in mobile_devices.router.routes if r.path == "/me")
    dependency_calls = [d.call for d in route.dependant.dependencies]
    assert mobile_devices._device_jwt_auth in dependency_calls


@pytest.mark.asyncio
async def test_device_me_returns_identity_and_updates_last_seen(db_session, paired_device):
    """A device JWT caller gets its identity back and last_seen_at refreshes."""
    old_seen = paired_device.last_seen_at
    client = _client(
        db_session,
        {
            "device_id": str(paired_device.id),
            "user_id": _USER_ID,
            "scope": "read",
            "auth_method": "device_jwt",
        },
    )

    response = client.get("/api/devices/me")

    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == str(paired_device.id)
    assert data["user_id"] == _USER_ID
    assert data["scope"] == "read"
    assert data["last_seen_at"] is not None

    result = await db_session.execute(select(MobileDevice).where(MobileDevice.id == paired_device.id))
    refreshed = result.scalar_one()
    assert refreshed.last_seen_at.replace(tzinfo=None) > old_seen.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_device_me_unknown_device_returns_403(db_session):
    """A token for a device row that no longer exists is rejected (revoked)."""
    client = _client(
        db_session,
        {
            "device_id": str(uuid.uuid4()),
            "user_id": "ghost-user",
            "scope": "read",
            "auth_method": "device_jwt",
        },
    )

    response = client.get("/api/devices/me")
    assert response.status_code == 403
    assert "revoked" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_device_me_malformed_device_id_returns_401(db_session):
    """A non-UUID device_id claim cannot reach the database query."""
    client = _client(
        db_session,
        {
            "device_id": "not-a-uuid",
            "user_id": "ghost-user",
            "scope": "read",
            "auth_method": "device_jwt",
        },
    )

    response = client.get("/api/devices/me")
    assert response.status_code == 401
