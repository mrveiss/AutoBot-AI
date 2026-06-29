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

import uuid
from datetime import timedelta
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
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc
from models.mobile_device import MobileDevice
from user_management.models.base import Base

# Test database setup
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


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
        await conn.run_sync(Base.metadata.create_all)

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


@pytest.fixture
def redis_client():
    """Get Redis client for test."""
    client = get_redis_client(database="main")
    if client is None:
        pytest.skip("Redis not available")
    return client


@pytest.fixture(autouse=True)
def cleanup_redis(redis_client):
    """Clean up Redis keys before and after each test."""
    # Clean before
    pattern = "autobot:mobile_pair_challenge:*"
    for key in redis_client.scan_iter(match=pattern):
        redis_client.delete(key)

    yield

    # Clean after
    for key in redis_client.scan_iter(match=pattern):
        redis_client.delete(key)


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
    assert stored_user_id.decode() == test_user["id"]

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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
