# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GET /api/devices/me — require_device_jwt wiring tests (#11736).
GET /api/devices — device-JWT own-device response scoping tests (#11792).

Separate from test_mobile_pairing.py on purpose: that module's autouse
Redis-cleanup fixture skips the whole file when Redis is unavailable
(CI included), and these tests need only the in-memory database. Keeping
them here guarantees the #11736/#11792 wiring is always exercised.
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
from auth_middleware import get_current_user
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


def _client(db_session, device_user: dict | None = None, current_user: dict | None = None) -> TestClient:
    """Client with the DB and device-JWT dependencies overridden.

    ``device_user`` overrides require_device_jwt (the /me route);
    ``current_user`` overrides get_current_user for the routes that accept
    both principals (the #11792 list-scoping tests) — pass the device-user
    dict (auth_method="device_jwt") or a plain user-session dict.
    """
    app = FastAPI()
    app.include_router(mobile_router, prefix="/api/devices")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    if device_user is not None:
        app.dependency_overrides[_device_jwt_auth] = lambda: device_user
    if current_user is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user
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


# ---------------------------------------------------------------------------
# GET /api/devices — device-JWT own-device response scoping (#11792)
# ---------------------------------------------------------------------------


def _device_principal(device_id: str, scope: str = "read") -> dict:
    """Synthetic device user as get_current_user attaches it (GH#9493)."""
    return {
        "device_id": device_id,
        "user_id": _USER_ID,
        "scope": scope,
        "auth_method": "device_jwt",
        "role": "device",
        "username": f"device:{device_id}",
    }


async def _add_device(db_session, name: str, user_id: str = _USER_ID) -> MobileDevice:
    """Seed an active sibling device (encryption stubbed by paired_device)."""
    device = MobileDevice(
        user_id=user_id,
        device_name=name,
        device_token=f"tok-{name}",
        platform="android",
        last_seen_at=now_utc(),
    )
    db_session.add(device)
    await db_session.commit()
    return device


@pytest.mark.asyncio
async def test_list_devices_device_jwt_scoped_to_own_device(db_session, paired_device):
    """A device read token GETs /api/devices and sees EXACTLY its own record."""
    sibling = await _add_device(db_session, "Sibling Tablet")
    client = _client(db_session, current_user=_device_principal(str(paired_device.id)))

    response = client.get("/api/devices")

    assert response.status_code == 200
    devices = response.json()["devices"]
    assert [d["id"] for d in devices] == [str(paired_device.id)]
    assert str(sibling.id) not in {d["id"] for d in devices}


@pytest.mark.asyncio
async def test_list_devices_write_device_token_also_own_scoped(db_session, paired_device):
    """Own-device scoping keys off auth_method, not scope — write tokens too."""
    await _add_device(db_session, "Sibling Tablet")
    client = _client(db_session, current_user=_device_principal(str(paired_device.id), scope="write"))

    response = client.get("/api/devices")

    assert response.status_code == 200
    assert [d["id"] for d in response.json()["devices"]] == [str(paired_device.id)]


@pytest.mark.asyncio
async def test_list_devices_user_session_gets_full_list(db_session, paired_device):
    """Zero regression: user-session callers keep the unfiltered full list."""
    sibling = await _add_device(db_session, "Sibling Tablet")
    client = _client(db_session, current_user={"id": _USER_ID, "user_id": _USER_ID})

    response = client.get("/api/devices")

    assert response.status_code == 200
    ids = {d["id"] for d in response.json()["devices"]}
    assert ids == {str(paired_device.id), str(sibling.id)}


@pytest.mark.asyncio
async def test_list_devices_malformed_device_principal_returns_401(db_session, paired_device):
    """A non-UUID device_id claim cannot reach the list query."""
    client = _client(db_session, current_user=_device_principal("not-a-uuid"))

    response = client.get("/api/devices")
    assert response.status_code == 401
