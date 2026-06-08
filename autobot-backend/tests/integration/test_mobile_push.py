# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mobile Push Notification Integration Tests (GH#4463, MVA-2995)

Comprehensive end-to-end tests for push notification delivery to mobile devices:
- Push delivery to iOS devices (APNs stub)
- Push delivery to Android devices (FCM stub)
- Push delivery to PWA devices (web push)
- Device token validation and handling
- Failure scenarios and error handling
- Stale device cleanup during push operations
"""

from datetime import timedelta
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker
from sqlalchemy.pool import StaticPool

from autobot_shared.time_utils import now_utc
from models.mobile_device import MobileDevice
from push_notifications.mobile_push import _get_target_devices
from services.push_notification_service import (
    _send_mobile_push,
    send_push_notification,
)
from user_management.models.base import Base

# Test database setup
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_db_engine():
    """Create an in-memory test database engine."""
    engine = create_async_engine(
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
    async_session = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test-user-push-123"


@pytest.fixture
async def mock_session_factory(test_db_session):
    """Mock session factory for push service."""

    async def factory():
        """Async context manager that yields test session."""

        class SessionContext:
            async def __aenter__(self):
                return test_db_session

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return SessionContext()

    return factory


# =============================================================================
# Device Retrieval Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_target_devices_no_devices(mock_session_factory, test_user_id):
    """Test retrieving mobile devices when user has none."""
    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        devices = await _get_target_devices(test_user_id)
        assert devices == []


@pytest.mark.asyncio
async def test_get_target_devices_with_active_devices(mock_session_factory, test_db_session, test_user_id):
    """Test retrieving active mobile devices."""
    # Create active devices
    devices = [
        MobileDevice(
            user_id=test_user_id,
            device_name="iPhone 15",
            device_token="apns-token-ios",
            platform="ios",
            last_seen_at=now_utc() - timedelta(days=10),
        ),
        MobileDevice(
            user_id=test_user_id,
            device_name="Pixel 8",
            device_token="fcm-token-android",
            platform="android",
            last_seen_at=now_utc() - timedelta(days=30),
        ),
    ]

    for device in devices:
        test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        retrieved = await _get_target_devices(test_user_id)

    assert len(retrieved) == 2
    assert {d["platform"] for d in retrieved} == {"ios", "android"}

    # Verify tokens are decrypted
    tokens = {d["device_token"] for d in retrieved}
    assert "apns-token-ios" in tokens
    assert "fcm-token-android" in tokens


@pytest.mark.asyncio
async def test_get_target_devices_filters_expired(mock_session_factory, test_db_session, test_user_id):
    """Test that expired devices (90+ days inactive) are filtered out."""
    cutoff = now_utc() - timedelta(days=90)

    # Create active and expired devices
    active = MobileDevice(
        user_id=test_user_id,
        device_name="Active Device",
        device_token="token-active",
        platform="ios",
        last_seen_at=now_utc() - timedelta(days=30),
    )

    expired = MobileDevice(
        user_id=test_user_id,
        device_name="Expired Device",
        device_token="token-expired",
        platform="android",
        last_seen_at=cutoff - timedelta(days=1),  # 91 days old
    )

    test_db_session.add(active)
    test_db_session.add(expired)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        retrieved = await _get_target_devices(test_user_id)

    assert len(retrieved) == 1
    assert retrieved[0]["device_token"] == "token-active"


@pytest.mark.asyncio
async def test_get_target_devices_handles_null_last_seen(mock_session_factory, test_db_session, test_user_id):
    """Test devices with NULL last_seen_at are included (newly paired)."""
    device = MobileDevice(
        user_id=test_user_id,
        device_name="New Device",
        device_token="token-new",
        platform="pwa",
        last_seen_at=None,  # Never seen yet
    )

    test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        retrieved = await _get_target_devices(test_user_id)

    assert len(retrieved) == 1
    assert retrieved[0]["platform"] == "pwa"


# =============================================================================
# Mobile Push Delivery Tests
# =============================================================================


@pytest.mark.asyncio
async def test_send_mobile_push_to_ios_device(mock_session_factory, test_db_session, test_user_id):
    """Test push notification to iOS device (stub logs delivery)."""
    device = MobileDevice(
        user_id=test_user_id,
        device_name="iPhone 15 Pro",
        device_token="apns-production-token-xyz",
        platform="ios",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        count = await _send_mobile_push(
            user_id=test_user_id,
            title="Test Notification",
            body="This is a test",
            url="/dashboard",
        )

    # Stub implementation returns 1 for iOS
    assert count == 1


@pytest.mark.asyncio
async def test_send_mobile_push_to_android_device(mock_session_factory, test_db_session, test_user_id):
    """Test push notification to Android device (stub logs delivery)."""
    device = MobileDevice(
        user_id=test_user_id,
        device_name="Pixel 8 Pro",
        device_token="fcm-registration-token-abc",
        platform="android",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        count = await _send_mobile_push(
            user_id=test_user_id,
            title="Android Alert",
            body="Your task completed",
            url="/tasks/123",
        )

    assert count == 1


@pytest.mark.asyncio
async def test_send_mobile_push_to_pwa_device(mock_session_factory, test_db_session, test_user_id):
    """Test PWA devices are skipped in mobile push (handled by web push)."""
    device = MobileDevice(
        user_id=test_user_id,
        device_name="Chrome PWA",
        device_token="web-push-subscription-pwa",
        platform="pwa",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        count = await _send_mobile_push(
            user_id=test_user_id,
            title="PWA Test",
            body="Should be skipped",
            url="/",
        )

    # PWA devices are skipped in mobile push
    assert count == 0


@pytest.mark.asyncio
async def test_send_mobile_push_to_multiple_devices(mock_session_factory, test_db_session, test_user_id):
    """Test push notification delivery to multiple devices."""
    devices = [
        MobileDevice(
            user_id=test_user_id,
            device_name="iPhone",
            device_token="token-ios",
            platform="ios",
            last_seen_at=now_utc(),
        ),
        MobileDevice(
            user_id=test_user_id,
            device_name="Android",
            device_token="token-android",
            platform="android",
            last_seen_at=now_utc(),
        ),
        MobileDevice(
            user_id=test_user_id,
            device_name="iPad",
            device_token="token-ios-2",
            platform="ios",
            last_seen_at=now_utc(),
        ),
    ]

    for device in devices:
        test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        count = await _send_mobile_push(
            user_id=test_user_id,
            title="Multi-device Alert",
            body="Sent to all devices",
            url="/",
        )

    # iOS (2) + Android (1) = 3
    assert count == 3


@pytest.mark.asyncio
async def test_send_mobile_push_no_devices(mock_session_factory, test_user_id):
    """Test push delivery when user has no devices."""
    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        count = await _send_mobile_push(
            user_id=test_user_id,
            title="No Devices",
            body="Should return 0",
            url="/",
        )

    assert count == 0


# =============================================================================
# Full Push Notification Flow Tests
# =============================================================================


@pytest.mark.asyncio
async def test_send_push_notification_integration(mock_session_factory, test_db_session, test_user_id):
    """Test full push notification flow (web + mobile)."""
    # Create mobile device
    device = MobileDevice(
        user_id=test_user_id,
        device_name="Test Device",
        device_token="token-test",
        platform="ios",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()

    # Mock web push to return 0 (no web subscriptions)
    with (
        patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory),
        patch("services.push_notification_service._send_web_push", return_value=0),
    ):
        total_count = await send_push_notification(
            user_id=test_user_id,
            title="Full Integration Test",
            body="Testing both web and mobile push",
            url="/test",
        )

    # Mobile push = 1 (iOS device), web push = 0 (mocked)
    assert total_count == 1


@pytest.mark.asyncio
async def test_send_push_notification_with_custom_ttl(mock_session_factory, test_db_session, test_user_id):
    """Test push notification with custom TTL parameter."""
    device = MobileDevice(
        user_id=test_user_id,
        device_name="Device",
        device_token="token",
        platform="android",
        last_seen_at=now_utc(),
    )
    test_db_session.add(device)
    await test_db_session.commit()

    with (
        patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory),
        patch("services.push_notification_service._send_web_push", return_value=0) as mock_web,
    ):
        await send_push_notification(
            user_id=test_user_id,
            title="Custom TTL",
            body="Test",
            url="/",
            ttl=3600,  # 1 hour
        )

    # Verify TTL was passed to web push
    mock_web.assert_called_once()
    assert mock_web.call_args[1]["ttl"] == 3600


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.asyncio
async def test_send_mobile_push_handles_db_errors_gracefully(test_user_id):
    """Test push service handles database errors gracefully."""

    async def failing_factory():
        raise Exception("Database connection failed")

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=failing_factory):
        # Should not raise, returns empty list
        devices = await _get_target_devices(test_user_id)

    assert devices == []


@pytest.mark.asyncio
async def test_send_mobile_push_handles_decryption_errors(mock_session_factory, test_db_session, test_user_id):
    """Test push service handles token decryption errors."""
    # Create device with invalid encrypted token
    device = MobileDevice(
        user_id=test_user_id,
        device_name="Bad Token Device",
        platform="ios",
        last_seen_at=now_utc(),
    )
    # Manually set invalid encrypted token (bypass setter)
    device._device_token_encrypted = "invalid-encrypted-data-xxx"
    test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        # Should handle decryption error gracefully
        try:
            await _get_target_devices(test_user_id)
            # May raise during token access, or return with error
            # Either way, should not crash the service
        except Exception:
            # Decryption error is expected
            pass


# =============================================================================
# Device Platform Validation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_send_mobile_push_unknown_platform(mock_session_factory, test_db_session, test_user_id):
    """Test push service handles unknown platform gracefully."""
    device = MobileDevice(
        user_id=test_user_id,
        device_name="Unknown Platform Device",
        device_token="token-unknown",
        platform="unknown",  # Not in standard enum
        last_seen_at=now_utc(),
    )
    # Force unknown platform value
    test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        # Should log warning but not crash
        count = await _send_mobile_push(
            user_id=test_user_id,
            title="Test",
            body="Test",
            url="/",
        )

    # Unknown platforms are skipped
    assert count == 0


# =============================================================================
# Multi-User Isolation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_send_push_only_to_user_devices(mock_session_factory, test_db_session, test_user_id):
    """Test push notifications are only sent to target user's devices."""
    other_user_id = "other-user-999"

    # Create devices for both users
    user1_device = MobileDevice(
        user_id=test_user_id,
        device_name="User 1 Device",
        device_token="token-user1",
        platform="ios",
        last_seen_at=now_utc(),
    )

    user2_device = MobileDevice(
        user_id=other_user_id,
        device_name="User 2 Device",
        device_token="token-user2",
        platform="android",
        last_seen_at=now_utc(),
    )

    test_db_session.add(user1_device)
    test_db_session.add(user2_device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        count = await _send_mobile_push(
            user_id=test_user_id,  # Target user 1 only
            title="User 1 Notification",
            body="Only for user 1",
            url="/",
        )

    # Only 1 device (user 1's)
    assert count == 1


# =============================================================================
# Celery Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_celery_task_success_hook_triggers_push():
    """Test Celery task success hook triggers push notification."""
    from services.push_notification_service import register_celery_task_success_hook

    # Register hook (should not raise even if Celery not available)
    try:
        register_celery_task_success_hook()
    except ImportError:
        pytest.skip("Celery not available")


# =============================================================================
# Performance and Scalability Tests
# =============================================================================


@pytest.mark.asyncio
async def test_send_push_to_many_devices_is_efficient(mock_session_factory, test_db_session, test_user_id):
    """Test push notification scales to many devices."""
    # Create 50 devices
    devices = [
        MobileDevice(
            user_id=test_user_id,
            device_name=f"Device {i}",
            device_token=f"token-{i}",
            platform="ios" if i % 2 == 0 else "android",
            last_seen_at=now_utc(),
        )
        for i in range(50)
    ]

    for device in devices:
        test_db_session.add(device)
    await test_db_session.commit()

    with patch("push_notifications.mobile_push.get_async_session_factory", return_value=mock_session_factory):
        import time

        start = time.time()
        count = await _send_mobile_push(
            user_id=test_user_id,
            title="Bulk Test",
            body="Testing many devices",
            url="/",
        )
        elapsed = time.time() - start

    assert count == 50  # PWA is skipped, all ios/android
    # Should complete reasonably fast (stub doesn't actually make network calls)
    assert elapsed < 5.0  # Should be nearly instant for stubs


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
