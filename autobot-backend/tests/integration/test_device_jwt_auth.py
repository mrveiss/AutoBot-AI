# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for device JWT authentication and scoping (MVA-3237).

Tests:
- Device pairing generates valid JWT
- Device JWT authenticates API requests
- Read-only scope enforcement
- Admin scope bypass (when implemented)
- JWT expiry handling
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request, status

from auth_middleware import enforce_device_read_only_scope, get_auth_middleware
from models.mobile_device import DeviceTokenScope
from services.device_jwt import mint_device_jwt, validate_device_jwt


class TestDeviceJWTGeneration:
    """Test device JWT generation during pairing."""

    def test_mint_device_jwt_read_only_scope(self):
        """JWT should contain correct claims for read-only device."""
        device_id = uuid.uuid4()
        user_id = "user123"

        token = mint_device_jwt(
            device_id=device_id,
            user_id=user_id,
            scope=DeviceTokenScope.READ_ONLY.value,
        )

        # Should be a non-empty string
        assert isinstance(token, str)
        assert len(token) > 0

        # Should be decodable with correct claims
        claims = validate_device_jwt(token)
        assert claims["sub"] == str(device_id)
        assert claims["user_id"] == user_id
        assert claims["scope"] == "read-only"
        assert claims["type"] == "device_token"
        assert "exp" in claims

    def test_mint_device_jwt_admin_scope(self):
        """JWT should contain correct claims for admin device."""
        device_id = uuid.uuid4()
        user_id = "user456"

        token = mint_device_jwt(
            device_id=device_id,
            user_id=user_id,
            scope=DeviceTokenScope.ADMIN.value,
        )

        claims = validate_device_jwt(token)
        assert claims["scope"] == "admin"


class TestDeviceJWTValidation:
    """Test device JWT validation."""

    def test_validate_device_jwt_success(self):
        """Valid JWT should decode successfully."""
        device_id = uuid.uuid4()
        user_id = "user789"
        token = mint_device_jwt(device_id, user_id)

        claims = validate_device_jwt(token)

        assert claims["sub"] == str(device_id)
        assert claims["user_id"] == user_id
        assert claims["scope"] == "read-only"
        assert claims["type"] == "device_token"

    def test_validate_device_jwt_wrong_type(self):
        """JWT with wrong type claim should be rejected."""
        from autobot_shared.auth.jwt_core import JWTDecodeError, encode_jwt

        # Create a JWT with wrong type
        payload = {
            "sub": str(uuid.uuid4()),
            "user_id": "user123",
            "scope": "read-only",
            "type": "user_token",  # Wrong type
        }

        # Use same secret as device JWT
        import os
        secret = os.environ.get("DEVICE_JWT_SECRET") or os.environ.get("AUTOBOT_JWT_SECRET", "test-secret")
        token = encode_jwt(payload, secret=secret, expires_delta=timedelta(days=1))

        with pytest.raises(JWTDecodeError, match="not a device token"):
            validate_device_jwt(token)

    def test_validate_device_jwt_missing_claims(self):
        """JWT missing required claims should be rejected."""
        from autobot_shared.auth.jwt_core import JWTDecodeError, encode_jwt

        # Create a JWT missing required claims
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "device_token",
            # Missing user_id and scope
        }

        import os
        secret = os.environ.get("DEVICE_JWT_SECRET") or os.environ.get("AUTOBOT_JWT_SECRET", "test-secret")
        token = encode_jwt(payload, secret=secret, expires_delta=timedelta(days=1))

        with pytest.raises(JWTDecodeError, match="missing required claims"):
            validate_device_jwt(token)


class TestDeviceJWTAuthentication:
    """Test device JWT authentication in middleware."""

    def test_extract_user_from_device_jwt(self):
        """Middleware should extract user from valid device JWT."""
        device_id = uuid.uuid4()
        user_id = "user123"
        token = mint_device_jwt(device_id, user_id, scope="read-only")

        # Create mock request with Authorization header
        request = MagicMock(spec=Request)
        request.headers.get.return_value = f"Bearer {token}"

        middleware = get_auth_middleware()
        user_data = middleware._extract_user_from_device_jwt(request)

        assert user_data is not None
        assert user_data["user_id"] == user_id
        assert user_data["device_id"] == str(device_id)
        assert user_data["scope"] == "read-only"
        assert user_data["auth_method"] == "device_jwt"
        assert user_data["role"] == "device"
        assert user_data["username"].startswith("device:")

    def test_extract_user_from_device_jwt_no_bearer(self):
        """Middleware should return None when no Bearer token present."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = None

        middleware = get_auth_middleware()
        user_data = middleware._extract_user_from_device_jwt(request)

        assert user_data is None

    def test_extract_user_from_device_jwt_invalid_token(self):
        """Middleware should return None for invalid tokens."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "Bearer invalid_token"

        middleware = get_auth_middleware()
        user_data = middleware._extract_user_from_device_jwt(request)

        assert user_data is None


class TestDeviceScopeEnforcement:
    """Test device token scope enforcement."""

    @pytest.mark.asyncio
    async def test_get_current_user_rejects_device_jwt(self):
        """get_current_user should reject device JWTs by default (fail-closed security)."""
        from auth_middleware import get_current_user

        device_id = uuid.uuid4()
        user_id = "user123"
        token = mint_device_jwt(device_id, user_id, scope="read-only")

        request = MagicMock(spec=Request)
        request.headers.get.return_value = f"Bearer {token}"
        request.url.path = "/api/conversations"

        # get_current_user should reject device JWTs
        with pytest.raises(Exception) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Device tokens not permitted" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_require_device_jwt_read_only_success(self):
        """require_device_jwt should accept read-only device tokens."""
        from auth_middleware import require_device_jwt

        device_id = uuid.uuid4()
        user_id = "user123"
        token = mint_device_jwt(device_id, user_id, scope="read-only")

        request = MagicMock(spec=Request)
        request.headers.get.return_value = f"Bearer {token}"

        # Mock database check for device existence
        with patch("auth_middleware.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_device = MagicMock()
            mock_device.id = device_id

            mock_result.scalar_one_or_none.return_value = mock_device
            mock_session.execute.return_value = mock_result
            mock_session.close = MagicMock()

            async def mock_session_gen():
                yield mock_session

            mock_get_db.return_value = mock_session_gen()

            user_data = await require_device_jwt(request, min_scope="read-only")

            assert user_data["user_id"] == user_id
            assert user_data["scope"] == "read-only"
            assert user_data["auth_method"] == "device_jwt"

    @pytest.mark.asyncio
    async def test_require_device_jwt_admin_rejected(self):
        """require_device_jwt with admin scope should reject read-only tokens."""
        from auth_middleware import require_device_jwt

        device_id = uuid.uuid4()
        user_id = "user123"
        token = mint_device_jwt(device_id, user_id, scope="read-only")

        request = MagicMock(spec=Request)
        request.headers.get.return_value = f"Bearer {token}"

        # Mock database check
        with patch("auth_middleware.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_device = MagicMock()
            mock_device.id = device_id
            mock_result.scalar_one_or_none.return_value = mock_device
            mock_session.execute.return_value = mock_result
            mock_session.close = MagicMock()

            async def mock_session_gen():
                yield mock_session

            mock_get_db.return_value = mock_session_gen()

            with pytest.raises(Exception) as exc_info:
                await require_device_jwt(request, min_scope="admin")

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "admin scope" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_require_device_jwt_revoked_device(self):
        """require_device_jwt should reject tokens for deleted devices."""
        from auth_middleware import require_device_jwt

        device_id = uuid.uuid4()
        user_id = "user123"
        token = mint_device_jwt(device_id, user_id, scope="read-only")

        request = MagicMock(spec=Request)
        request.headers.get.return_value = f"Bearer {token}"

        # Mock database check - device not found (deleted)
        with patch("auth_middleware.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # Device deleted
            mock_session.execute.return_value = mock_result
            mock_session.close = MagicMock()

            async def mock_session_gen():
                yield mock_session

            mock_get_db.return_value = mock_session_gen()

            with pytest.raises(Exception) as exc_info:
                await require_device_jwt(request)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "revoked" in str(exc_info.value.detail)
