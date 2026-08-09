# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Mobile Device Pairing Integration Tests (GH#4463, MVA-2995)

Comprehensive end-to-end tests for the mobile device pairing flow:
- QR challenge token generation and expiry
- Device pairing with valid/expired/reused tokens
- Device listing with auto-pruning
- Device unpairing
- Multi-platform support (iOS/Android/PWA)
- Security: token encryption, one-time use, user isolation
"""

import asyncio
import uuid
from datetime import timedelta
from fnmatch import fnmatch
from time import monotonic
from typing import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker
from sqlalchemy.pool import StaticPool

from api.mobile_devices import _QR_CHALLENGE_TTL_SECONDS, _redis_challenge_key
from api.mobile_devices import router as mobile_router
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.time_utils import now_utc
from models.mobile_device import MobileDevice
from user_management.models.base import Base

# Test database setup
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _test_encryption_service(monkeypatch):
    """Provide a REAL EncryptionService with an injected test master key (#11687).

    ``MobileDevice.device_token`` encrypts/decrypts through the module-level
    ``get_encryption_service()`` singleton, which requires
    ``AUTOBOT_ENCRYPTION_KEY`` — absent in the hermetic test env (ssot config
    reads env once at import, so setting the variable here would be too late).
    Injecting the key keeps the real AES-GCM round-trip under test (same
    pattern already used by the sibling test_mobile_push.py).
    """
    import encryption_service as enc_mod

    svc = enc_mod.EncryptionService(master_key="integration-test-master-key-0123456789abcdef")
    monkeypatch.setattr(enc_mod, "get_encryption_service", lambda: svc)
    # device_jwt.py's _secret() reads DEVICE_JWT_SECRET fresh from os.environ
    # on every call (no import-time caching, unlike the encryption key above),
    # so a plain monkeypatch.setenv is sufficient — same convention already
    # used by services/device_jwt_test.py.
    monkeypatch.setenv("DEVICE_JWT_SECRET", "test-secret-32-chars-minimum-len")


@pytest.fixture
async def test_db_engine():
    """Create an in-memory test database engine."""
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        # #11834: scope create_all to the tables under test — whole-metadata
        # create_all breaks under whole-dir order when earlier tests import
        # llc models whose Postgres '::jsonb' server_defaults sqlite rejects
        # (same fix already applied in the sibling test_mobile_push.py).
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[MobileDevice.__table__]))

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture
def test_user():
    """Mock test user."""
    return {
        "id": "test-user-123",
        "user_id": "test-user-123",
        "email": "test@example.com",
    }


@pytest.fixture
def test_user_2():
    """Second mock test user for isolation tests."""
    return {
        "id": "test-user-456",
        "user_id": "test-user-456",
        "email": "test2@example.com",
    }


@pytest.fixture
def test_client(test_db_session, test_user):
    """Create a test FastAPI client with mocked dependencies."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(mobile_router, prefix="/api/devices")

    async def override_get_db():
        yield test_db_session

    def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    return TestClient(app)


class _FakeRedis:
    """In-process stand-in for the sync Redis client the pairing endpoints use.

    Implements exactly the surface ``api/mobile_devices.py`` touches — ``setex``
    / ``get`` / ``delete`` — plus ``ttl`` and ``scan_iter`` for the assertions in
    this file, with genuine expiry semantics (monotonic deadlines) and the
    ``decode_responses=True`` string values the production client is configured
    with. That keeps every behaviour under test real: one-time-use consumption,
    expiry, per-user binding and cross-request key visibility.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}
        # #13408: call counts, so a test can assert that token consumption goes
        # through the atomic GETDEL rather than a separate GET then DELETE.
        self.calls: dict[str, int] = {"get": 0, "delete": 0, "getdel": 0}

    def _read(self, key: str) -> tuple[str, float] | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry[1] <= monotonic():
            del self._store[key]
            return None
        return entry

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self._store[key] = (str(value), monotonic() + int(ttl_seconds))
        return True

    def get(self, key: str) -> str | None:
        self.calls["get"] += 1
        entry = self._read(key)
        return None if entry is None else entry[0]

    def delete(self, *keys: str) -> int:
        self.calls["delete"] += 1
        return sum(1 for key in keys if self._store.pop(key, None) is not None)

    def getdel(self, key: str) -> str | None:
        """Atomically return a key's value and remove it (Redis 6.2 GETDEL).

        #13408: the real client exposes this and ``client_getdel`` prefers it.
        A double without it would silently push the code under test down the
        non-atomic GET+DELETE fallback — the double would then be testing a
        path production never takes, which is how a single-use control can look
        covered while the race it exists to prevent goes untested.
        """
        self.calls["getdel"] += 1
        entry = self._read(key)
        if entry is None:
            return None
        del self._store[key]
        return entry[0]

    def ttl(self, key: str) -> int:
        entry = self._read(key)
        # Redis returns -2 for a missing key, -1 for a key with no expiry.
        return -2 if entry is None else max(1, int(entry[1] - monotonic()))

    def scan_iter(self, match: str = "*"):
        return iter([key for key in list(self._store) if fnmatch(key, match)])


class _FakeAsyncRedis:
    """Async view over the same store, for callers that await their client.

    ``DELETE /api/devices/{id}`` invalidates the device-JWT cache through
    ``services.device_jwt.invalidate_device_cache``, which awaits
    ``get_async_redis_client()``. Left unbound that dials the configured Redis
    host and burns the full connect/retry budget — ~30 s in
    ``test_unpair_device_success`` alone — before falling through its
    ``if redis is None`` branch, so the invalidation was never actually
    exercised. Sharing the sync double's store keeps it exercised and instant.
    """

    def __init__(self, sync_client: "_FakeRedis") -> None:
        self._sync = sync_client

    async def get(self, key: str) -> str | None:
        return self._sync.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        return self._sync.setex(key, ttl_seconds, value)

    async def delete(self, *keys: str) -> int:
        return self._sync.delete(*keys)


@pytest.fixture(autouse=True)
def redis_client(monkeypatch):
    """Bind the pairing endpoints to a deterministic in-process Redis double.

    #13162: this fixture used to hand back ``get_redis_client(database="main")``
    and ``pytest.skip`` when it returned ``None``. That guard cannot detect the
    only failure mode that actually occurs in CI — the backend test harness
    stubs ``autobot_shared.redis_client``, so the call returns a truthy
    ``MagicMock`` rather than ``None``. The suite then ran against a mock whose
    ``get()`` answers every lookup with a fresh ``MagicMock``: the challenge
    token never round-tripped, and ``POST /pair`` wrote a ``MagicMock`` into the
    ``user_id`` column, so SQLite rejected the INSERT and seven tests reported
    500-vs-201. Locally the same guard skipped all nineteen, so the pairing
    endpoints were verified in neither environment.

    Injecting the double removes the ambient dependency entirely and pins the
    name the router resolves (``api.mobile_devices`` binds ``get_redis_client``
    at import), so the tests exercise the real endpoint logic everywhere.
    """
    import api.mobile_devices as mobile_devices_module
    import services.device_jwt as device_jwt_module

    client = _FakeRedis()
    async_client = _FakeAsyncRedis(client)

    async def _get_async_client(**_kwargs):
        return async_client

    monkeypatch.setattr(mobile_devices_module, "get_redis_client", lambda **_kwargs: client)
    monkeypatch.setattr(device_jwt_module, "get_async_redis_client", _get_async_client)
    return client


# =============================================================================
# QR Challenge Token Tests
# =============================================================================


@pytest.mark.asyncio
async def test_generate_qr_challenge_token(test_client, redis_client, test_user):
    """Test QR challenge token generation creates valid token in Redis."""
    response = test_client.get("/api/devices/pair-qr")

    assert response.status_code == 200
    data = response.json()

    assert "challenge_token" in data
    assert "expires_in_seconds" in data
    assert data["expires_in_seconds"] == _QR_CHALLENGE_TTL_SECONDS
    assert len(data["challenge_token"]) > 20  # URL-safe token should be reasonably long

    # Verify token exists in Redis with correct user_id
    key = _redis_challenge_key(data["challenge_token"])
    stored_user_id = redis_client.get(key)
    assert stored_user_id is not None
    # get_redis_client() is configured with decode_responses=True (see
    # autobot_shared/redis_management/config.py), so values are already str.
    assert stored_user_id == test_user["id"]

    # Verify TTL is set correctly
    ttl = redis_client.ttl(key)
    assert ttl > 0
    assert ttl <= _QR_CHALLENGE_TTL_SECONDS


@pytest.mark.asyncio
async def test_qr_challenge_token_uniqueness(test_client):
    """Test that multiple QR challenge requests generate unique tokens."""
    response1 = test_client.get("/api/devices/pair-qr")
    response2 = test_client.get("/api/devices/pair-qr")

    assert response1.status_code == 200
    assert response2.status_code == 200

    token1 = response1.json()["challenge_token"]
    token2 = response2.json()["challenge_token"]

    assert token1 != token2


@pytest.mark.asyncio
async def test_qr_challenge_without_user_returns_401(test_client):
    """Test QR challenge generation fails without authenticated user."""
    # Override to return invalid user
    from auth_middleware import get_current_user

    def override_no_user():
        return {}  # No user ID

    test_client.app.dependency_overrides[get_current_user] = override_no_user

    response = test_client.get("/api/devices/pair-qr")
    assert response.status_code == 401
    assert "User identity missing" in response.json()["detail"]


# =============================================================================
# Device Pairing Tests
# =============================================================================


@pytest.mark.asyncio
async def test_pair_device_success(test_client, test_db_session, redis_client, test_user):
    """Test successful device pairing with valid challenge token."""
    # Generate QR challenge
    qr_response = test_client.get("/api/devices/pair-qr")
    challenge_token = qr_response.json()["challenge_token"]

    # Pair device
    pair_payload = {
        "challenge_token": challenge_token,
        "device_name": "iPhone 15 Pro",
        "device_token": "apns-token-abc123xyz789",
        "platform": "ios",
    }

    response = test_client.post("/api/devices/pair", json=pair_payload)

    assert response.status_code == 201
    data = response.json()
    assert "device_id" in data
    assert data["message"] == "Device paired successfully"

    # Verify device exists in database
    result = await test_db_session.execute(select(MobileDevice).where(MobileDevice.user_id == test_user["id"]))
    device = result.scalar_one_or_none()

    assert device is not None
    assert device.device_name == "iPhone 15 Pro"
    assert device.platform == "ios"
    assert device.device_token == "apns-token-abc123xyz789"  # Property auto-decrypts
    assert device.last_seen_at is not None

    # Verify token was consumed (deleted from Redis)
    key = _redis_challenge_key(challenge_token)
    assert redis_client.get(key) is None


@pytest.mark.asyncio
async def test_pair_device_all_platforms(test_client, test_db_session, test_user):
    """Test pairing devices for all supported platforms."""
    platforms = [
        ("ios", "iPhone 14", "apns-token-ios"),
        ("android", "Pixel 8", "fcm-token-android"),
        ("pwa", "Chrome PWA", "web-push-token-pwa"),
    ]

    for platform, device_name, token in platforms:
        # Generate fresh QR for each
        qr_response = test_client.get("/api/devices/pair-qr")
        challenge_token = qr_response.json()["challenge_token"]

        pair_payload = {
            "challenge_token": challenge_token,
            "device_name": device_name,
            "device_token": token,
            "platform": platform,
        }

        response = test_client.post("/api/devices/pair", json=pair_payload)
        assert response.status_code == 201, f"Failed to pair {platform} device"

    # Verify all three devices exist
    result = await test_db_session.execute(select(MobileDevice).where(MobileDevice.user_id == test_user["id"]))
    devices = result.scalars().all()
    assert len(devices) == 3

    # Verify each platform
    platforms_found = {d.platform for d in devices}
    assert platforms_found == {"ios", "android", "pwa"}


@pytest.mark.asyncio
async def test_pair_with_expired_token_fails(test_client, redis_client):
    """Test pairing fails with expired challenge token."""
    # Generate token
    qr_response = test_client.get("/api/devices/pair-qr")
    challenge_token = qr_response.json()["challenge_token"]

    # Manually expire the token by deleting from Redis
    key = _redis_challenge_key(challenge_token)
    redis_client.delete(key)

    # Attempt to pair
    pair_payload = {
        "challenge_token": challenge_token,
        "device_name": "iPhone",
        "device_token": "token123",
        "platform": "ios",
    }

    response = test_client.post("/api/devices/pair", json=pair_payload)

    assert response.status_code == 400
    assert "expired or invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pair_with_reused_token_fails(test_client):
    """Test challenge token can only be used once (no replay attacks)."""
    # Generate token
    qr_response = test_client.get("/api/devices/pair-qr")
    challenge_token = qr_response.json()["challenge_token"]

    pair_payload = {
        "challenge_token": challenge_token,
        "device_name": "Device 1",
        "device_token": "token1",
        "platform": "ios",
    }

    # First pairing succeeds
    response1 = test_client.post("/api/devices/pair", json=pair_payload)
    assert response1.status_code == 201

    # Second pairing with same token fails
    pair_payload["device_name"] = "Device 2"
    pair_payload["device_token"] = "token2"
    response2 = test_client.post("/api/devices/pair", json=pair_payload)

    assert response2.status_code == 400
    assert "expired or invalid" in response2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pair_with_invalid_token_fails(test_client):
    """Test pairing fails with non-existent challenge token."""
    pair_payload = {
        "challenge_token": "invalid-token-that-does-not-exist",
        "device_name": "iPhone",
        "device_token": "token123",
        "platform": "ios",
    }

    response = test_client.post("/api/devices/pair", json=pair_payload)

    assert response.status_code == 400
    assert "expired or invalid" in response.json()["detail"].lower()


# =============================================================================
# Device Listing Tests
# =============================================================================


@pytest.mark.asyncio
async def test_list_devices_empty(test_client):
    """Test listing devices when user has none."""
    response = test_client.get("/api/devices")

    assert response.status_code == 200
    data = response.json()
    assert "devices" in data
    assert data["devices"] == []


@pytest.mark.asyncio
async def test_list_devices_with_multiple_devices(test_client, test_db_session, test_user):
    """Test listing returns all user's devices."""
    # Create test devices
    devices = [
        MobileDevice(
            user_id=test_user["id"],
            device_name="iPhone 15",
            device_token="token-ios",
            platform="ios",
            last_seen_at=now_utc(),
        ),
        MobileDevice(
            user_id=test_user["id"],
            device_name="Pixel 8",
            device_token="token-android",
            platform="android",
            last_seen_at=now_utc(),
        ),
    ]

    for device in devices:
        test_db_session.add(device)
    await test_db_session.commit()

    # List devices
    response = test_client.get("/api/devices")

    assert response.status_code == 200
    data = response.json()
    assert len(data["devices"]) == 2

    # Verify device data
    device_names = {d["device_name"] for d in data["devices"]}
    assert device_names == {"iPhone 15", "Pixel 8"}

    # Verify response structure
    for device_data in data["devices"]:
        assert "id" in device_data
        assert "device_name" in device_data
        assert "platform" in device_data
        assert "last_seen_at" in device_data
        assert "created_at" in device_data
        # Token should NOT be exposed
        assert "device_token" not in device_data


@pytest.mark.asyncio
async def test_list_devices_auto_prunes_expired(test_client, test_db_session, test_user):
    """Test listing automatically removes devices inactive for 90+ days."""
    cutoff = now_utc() - timedelta(days=90)

    # Create active and expired devices
    active_device = MobileDevice(
        user_id=test_user["id"],
        device_name="Active iPhone",
        device_token="token-active",
        platform="ios",
        last_seen_at=now_utc() - timedelta(days=30),  # Active
    )

    expired_device = MobileDevice(
        user_id=test_user["id"],
        device_name="Expired Android",
        device_token="token-expired",
        platform="android",
        last_seen_at=cutoff - timedelta(days=1),  # 91 days old
    )

    test_db_session.add(active_device)
    test_db_session.add(expired_device)
    await test_db_session.commit()
    expired_id = expired_device.id

    # List devices - should prune expired
    response = test_client.get("/api/devices")

    assert response.status_code == 200
    data = response.json()
    assert len(data["devices"]) == 1
    assert data["devices"][0]["device_name"] == "Active iPhone"

    # Verify expired device was deleted from DB
    result = await test_db_session.execute(select(MobileDevice).where(MobileDevice.id == expired_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_list_devices_user_isolation(test_client, test_db_session, test_user, test_user_2):
    """Test users can only see their own devices."""
    # Create devices for both users
    user1_device = MobileDevice(
        user_id=test_user["id"],
        device_name="User 1 iPhone",
        device_token="token1",
        platform="ios",
        last_seen_at=now_utc(),
    )

    user2_device = MobileDevice(
        user_id=test_user_2["id"],
        device_name="User 2 Android",
        device_token="token2",
        platform="android",
        last_seen_at=now_utc(),
    )

    test_db_session.add(user1_device)
    test_db_session.add(user2_device)
    await test_db_session.commit()

    # List devices as user 1
    response = test_client.get("/api/devices")

    assert response.status_code == 200
    data = response.json()
    assert len(data["devices"]) == 1
    assert data["devices"][0]["device_name"] == "User 1 iPhone"


# =============================================================================
# Device Unpairing Tests
# =============================================================================


@pytest.mark.asyncio
async def test_unpair_device_success(test_client, test_db_session, test_user):
    """Test successful device unpairing."""
    # Create device
    device = MobileDevice(
        user_id=test_user["id"],
        device_name="iPhone to Delete",
        device_token="token-delete",
        platform="ios",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()
    device_id = device.id

    # Unpair device
    response = test_client.delete(f"/api/devices/{device_id}")

    assert response.status_code == 204

    # Verify device was deleted
    result = await test_db_session.execute(select(MobileDevice).where(MobileDevice.id == device_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_unpair_nonexistent_device_returns_404(test_client):
    """Test unpairing non-existent device returns 404."""
    fake_id = uuid.uuid4()
    response = test_client.delete(f"/api/devices/{fake_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unpair_other_user_device_returns_404(test_client, test_db_session, test_user, test_user_2):
    """Test users cannot unpair other users' devices."""
    # Create device for user 2
    device = MobileDevice(
        user_id=test_user_2["id"],
        device_name="User 2 Device",
        device_token="token-user2",
        platform="ios",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()
    device_id = device.id

    # Try to unpair as user 1
    response = test_client.delete(f"/api/devices/{device_id}")

    assert response.status_code == 404  # Not found (user isolation)

    # Verify device still exists
    result = await test_db_session.execute(select(MobileDevice).where(MobileDevice.id == device_id))
    assert result.scalar_one_or_none() is not None


# =============================================================================
# Token Encryption Tests
# =============================================================================


@pytest.mark.asyncio
async def test_device_token_encryption(test_db_session, test_user):
    """Test device tokens are encrypted at rest."""
    plaintext_token = "my-secret-apns-token-12345"

    device = MobileDevice(
        user_id=test_user["id"],
        device_name="Test Device",
        device_token=plaintext_token,  # Setter encrypts
        platform="ios",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()
    await test_db_session.refresh(device)

    # Verify encrypted value in DB is different from plaintext
    assert device._device_token_encrypted != plaintext_token

    # Verify decryption via property works
    assert device.device_token == plaintext_token


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


@pytest.mark.asyncio
async def test_pair_device_validates_platform(test_client):
    """Test pairing rejects invalid platform values."""
    qr_response = test_client.get("/api/devices/pair-qr")
    challenge_token = qr_response.json()["challenge_token"]

    pair_payload = {
        "challenge_token": challenge_token,
        "device_name": "Device",
        "device_token": "token",
        "platform": "invalid_platform",  # Not in enum
    }

    response = test_client.post("/api/devices/pair", json=pair_payload)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_pair_device_validates_required_fields(test_client):
    """Test pairing validates required fields."""
    qr_response = test_client.get("/api/devices/pair-qr")
    challenge_token = qr_response.json()["challenge_token"]

    # Missing device_name
    pair_payload = {
        "challenge_token": challenge_token,
        "device_token": "token",
        "platform": "ios",
    }

    response = test_client.post("/api/devices/pair", json=pair_payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_pairing_same_token_race_condition(test_client, redis_client):
    """Test concurrent pairing attempts with same token (race condition)."""
    # Generate token
    qr_response = test_client.get("/api/devices/pair-qr")
    challenge_token = qr_response.json()["challenge_token"]

    pair_payload = {
        "challenge_token": challenge_token,
        "device_name": "Device",
        "device_token": "token",
        "platform": "ios",
    }

    # First request succeeds
    response1 = test_client.post("/api/devices/pair", json=pair_payload)

    # Concurrent/immediate second request should fail (token consumed)
    response2 = test_client.post("/api/devices/pair", json=pair_payload)

    assert response1.status_code == 201
    assert response2.status_code == 400  # Token already consumed


@pytest.mark.asyncio
async def test_pairing_consumes_token_atomically(test_client, redis_client):
    """The challenge token is consumed with GETDEL, not GET-then-DELETE (#13408).

    ``test_concurrent_pairing_same_token_race_condition`` above cannot catch the
    race it is named for: ``TestClient`` is synchronous, so the first request has
    already finished — and deleted the key — before the second begins. The two
    calls never interleave, and a GET-then-DELETE implementation passes it.

    This asserts the property that actually closes the race: the read and the
    delete are one operation. With a separate GET and DELETE there is a window
    in which a second request reads a value the first has not yet removed, and
    both pair a device against the bound ``user_id`` — on an endpoint that is
    deliberately unauthenticated, where single-use is the entire control.
    """
    qr_response = test_client.get("/api/devices/pair-qr")
    challenge_token = qr_response.json()["challenge_token"]

    redis_client.calls["get"] = 0
    redis_client.calls["delete"] = 0
    redis_client.calls["getdel"] = 0

    response = test_client.post(
        "/api/devices/pair",
        json={
            "challenge_token": challenge_token,
            "device_name": "Device",
            "device_token": "token",
            "platform": "ios",
        },
    )

    assert response.status_code == 201
    assert redis_client.calls["getdel"] == 1, "challenge token was not consumed atomically"
    assert redis_client.calls["delete"] == 0, "a separate DELETE means the read and delete can interleave"


@pytest.mark.asyncio
async def test_only_one_of_two_interleaved_consumers_wins(redis_client):
    """Two consumers racing for one token: exactly one gets it (#13408).

    Drives ``client_getdel`` — the primitive the endpoint now uses — directly,
    concurrently, against the same key. This is the interleaving the endpoint
    test above cannot produce through a synchronous ``TestClient``.

    Scope, stated precisely: this pins the *primitive*. It does not observe the
    endpoint, so an endpoint that stopped calling ``client_getdel`` would still
    pass here — ``test_pairing_consumes_token_atomically`` above is what guards
    that, and it is the one verified to fail against a GET-then-DELETE
    implementation. The two are complementary and neither is sufficient alone.
    """
    from autobot_shared.redis_client import client_getdel

    key = _redis_challenge_key("race-token")
    redis_client.setex(key, 300, "user-42")

    results = await asyncio.gather(
        client_getdel(redis_client, key),
        client_getdel(redis_client, key),
    )

    assert sorted(r is None for r in results) == [False, True], f"expected exactly one winner, got {results!r}"
    assert redis_client.get(key) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
