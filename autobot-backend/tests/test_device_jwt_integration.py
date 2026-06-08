# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration tests for device JWT authentication (GH#9493)."""

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request, status
from fastapi.exceptions import HTTPException

from auth_middleware import get_current_user
from services.device_jwt import mint_device_jwt


@pytest.fixture(autouse=True)
def set_jwt_secret():
    """Set required JWT secret for all tests."""
    os.environ["DEVICE_JWT_SECRET"] = "test-secret-32-chars-minimum-len"
    os.environ["AUTOBOT_JWT_SECRET"] = "test-secret-32-chars-minimum-len"
    yield
    os.environ.pop("DEVICE_JWT_SECRET", None)
    os.environ.pop("AUTOBOT_JWT_SECRET", None)


@pytest.fixture
def mock_redis():
    """Mock Redis for device existence cache."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"1")  # Device exists by default
    redis.setex = AsyncMock()
    with patch("services.device_jwt.get_async_redis_client", return_value=redis):
        yield redis


@pytest.fixture
def mock_db_session():
    """Mock database session for device existence checks."""
    from unittest.mock import MagicMock

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=str(uuid.uuid4()))

    async def mock_get_async_session():
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)
        yield session

    with patch("user_management.database.get_async_session", side_effect=mock_get_async_session):
        yield result


class TestDeviceJWTAuthMiddleware:
    """Tests for device JWT authentication in auth middleware."""

    @pytest.mark.asyncio
    async def test_device_jwt_authenticates_on_devices_endpoint(self, mock_redis, mock_db_session):
        """Should authenticate device JWT on /api/devices/ endpoints (GH#9493)."""
        device_id = str(uuid.uuid4())
        user_id = "test-user-123"
        token = mint_device_jwt(device_id=device_id, user_id=user_id, scope="read")

        # Mock request to /api/devices/
        request = Request(
            {
                "type": "http",
                "path": "/api/devices/",
                "method": "GET",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        user_data = await get_current_user(request)
        assert user_data["auth_method"] == "device_jwt"
        assert user_data["device_id"] == device_id
        assert user_data["user_id"] == user_id
        assert user_data["scope"] == "read"

    @pytest.mark.asyncio
    async def test_device_jwt_blocked_on_non_devices_endpoint(self, mock_redis, mock_db_session):
        """Should block device JWT on non-/api/devices/ endpoints (GH#9493 narrow allow-list)."""
        device_id = str(uuid.uuid4())
        user_id = "test-user-123"
        token = mint_device_jwt(device_id=device_id, user_id=user_id, scope="read")

        # Mock request to /api/chat/ (not allowed)
        request = Request(
            {
                "type": "http",
                "path": "/api/chat/messages",
                "method": "GET",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Device JWT not permitted on this endpoint" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_read_scope_allows_get_requests(self, mock_redis, mock_db_session):
        """Should allow GET requests with read-scoped device JWT."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="read")

        request = Request(
            {
                "type": "http",
                "path": "/api/devices/",
                "method": "GET",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        user_data = await get_current_user(request)
        assert user_data["scope"] == "read"

    @pytest.mark.asyncio
    async def test_read_scope_blocks_post_requests(self, mock_redis, mock_db_session):
        """Should block POST with read-scoped JWT (GH#9493 scope enforcement)."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="read")

        request = Request(
            {
                "type": "http",
                "path": "/api/devices/",
                "method": "POST",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Read-only device JWT cannot use POST method" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_read_scope_blocks_delete_requests(self, mock_redis, mock_db_session):
        """Should block DELETE with read-scoped JWT (GH#9493 scope enforcement)."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="read")

        request = Request(
            {
                "type": "http",
                "path": "/api/devices/some-id",
                "method": "DELETE",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Read-only device JWT cannot use DELETE method" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_write_scope_allows_post_requests(self, mock_redis, mock_db_session):
        """Should allow POST with write-scoped JWT."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="write")

        request = Request(
            {
                "type": "http",
                "path": "/api/devices/",
                "method": "POST",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        user_data = await get_current_user(request)
        assert user_data["scope"] == "write"

    @pytest.mark.asyncio
    async def test_write_scope_allows_delete_requests(self, mock_redis, mock_db_session):
        """Should allow DELETE with write-scoped JWT."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="write")

        request = Request(
            {
                "type": "http",
                "path": "/api/devices/some-id",
                "method": "DELETE",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        user_data = await get_current_user(request)
        assert user_data["scope"] == "write"

    @pytest.mark.asyncio
    async def test_device_jwt_fails_when_device_deleted(self, mock_redis):
        """Should fail auth when device has been unpaired (GH#9493 revocation)."""
        from unittest.mock import MagicMock

        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="read")

        # Mock device does not exist (cache miss, DB returns None)
        mock_redis.get.return_value = None
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)

        async def mock_get_async_session_deleted():
            session = AsyncMock()
            session.execute = AsyncMock(return_value=result)
            yield session

        with patch("services.device_jwt.get_async_session", side_effect=mock_get_async_session_deleted):
            request = Request(
                {
                    "type": "http",
                    "path": "/api/devices/",
                    "method": "GET",
                    "headers": [(b"authorization", f"Bearer {token}".encode())],
                }
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)

            # Should fail with authentication required (device JWT validation failed)
            assert exc_info.value.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class TestScopeEnforcement:
    """Test matrix for scope + method combinations."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method,should_allow",
        [
            ("GET", True),
            ("HEAD", True),
            ("OPTIONS", True),
            ("POST", False),
            ("PUT", False),
            ("PATCH", False),
            ("DELETE", False),
        ],
    )
    async def test_read_scope_method_matrix(self, method, should_allow, mock_redis, mock_db_session):
        """Test all HTTP methods with read scope (GH#9493)."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="read")

        request = Request(
            {
                "type": "http",
                "path": "/api/devices/",
                "method": method,
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        if should_allow:
            user_data = await get_current_user(request)
            assert user_data["auth_method"] == "device_jwt"
        else:
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert f"Read-only device JWT cannot use {method} method" in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method",
        ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def test_write_scope_allows_all_methods(self, method, mock_redis, mock_db_session):
        """Write scope should allow all HTTP methods (GH#9493)."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id=device_id, user_id="test-user", scope="write")

        request = Request(
            {
                "type": "http",
                "path": "/api/devices/",
                "method": method,
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

        user_data = await get_current_user(request)
        assert user_data["auth_method"] == "device_jwt"
        assert user_data["scope"] == "write"
