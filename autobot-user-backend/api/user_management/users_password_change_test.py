# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Password Change API Endpoint

Tests rate limiting and password change functionality.
Issue #635.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from backend.user_management.middleware.rate_limit import RateLimitExceeded
from backend.user_management.services.user_service import (
    InvalidCredentialsError,
    UserNotFoundError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user_service():
    """Create mock user service."""
    service = AsyncMock()
    service.change_password = AsyncMock()
    return service


@pytest.fixture
def mock_rate_limiter():
    """Create mock rate limiter."""
    limiter = AsyncMock()
    limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
    limiter.record_attempt = AsyncMock()
    return limiter


@pytest.fixture
def user_id():
    """Generate test user ID."""
    return uuid.uuid4()


@pytest.fixture
def password_data():
    """Password change request data."""
    return {
        "current_password": "OldP@ssw0rd!",
        "new_password": "NewP@ssw0rd!",
    }


@pytest.fixture
def mock_current_user():
    """Mock current user with token."""
    return {
        "user_id": str(uuid.uuid4()),
        "token": "current.jwt.token.here",
    }


# ---------------------------------------------------------------------------
# Test: Rate Limiting
# ---------------------------------------------------------------------------


class TestPasswordChangeRateLimiting:
    """Tests for rate limiting on password change endpoint."""

    @pytest.mark.asyncio
    async def test_rate_limit_check_called_before_change(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
    ):
        """Rate limit should be checked before attempting password change."""
        with patch(
            "backend.api.user_management.users.PasswordChangeRateLimiter"
        ) as MockLimiter:
            mock_limiter = AsyncMock()
            mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
            mock_limiter.record_attempt = AsyncMock()
            MockLimiter.return_value = mock_limiter

            with patch(
                "backend.api.user_management.users.get_user_service",
                return_value=mock_user_service,
            ):
                from user_management.schemas import PasswordChange

                from backend.api.user_management.users import change_password

                pwd_change = PasswordChange(**password_data)
                await change_password(
                    user_id, pwd_change, mock_user_service, mock_current_user
                )

                mock_limiter.check_rate_limit.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
    ):
        """Should return 429 when rate limit is exceeded."""
        with patch(
            "backend.api.user_management.users.PasswordChangeRateLimiter"
        ) as MockLimiter:
            mock_limiter = AsyncMock()
            mock_limiter.check_rate_limit = AsyncMock(
                side_effect=RateLimitExceeded(
                    "Too many attempts. Try again in 15 minutes."
                )
            )
            MockLimiter.return_value = mock_limiter

            from fastapi import HTTPException
            from user_management.schemas import PasswordChange

            from backend.api.user_management.users import change_password

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await change_password(
                    user_id, pwd_change, mock_user_service, mock_current_user
                )

            assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            assert "Too many attempts" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_successful_change_clears_rate_limit(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
    ):
        """Successful password change should clear rate limit counter."""
        with patch(
            "backend.api.user_management.users.PasswordChangeRateLimiter"
        ) as MockLimiter:
            mock_limiter = AsyncMock()
            mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
            mock_limiter.record_attempt = AsyncMock()
            MockLimiter.return_value = mock_limiter

            from user_management.schemas import PasswordChange

            from backend.api.user_management.users import change_password

            pwd_change = PasswordChange(**password_data)
            await change_password(
                user_id, pwd_change, mock_user_service, mock_current_user
            )

            mock_limiter.record_attempt.assert_called_once_with(user_id, success=True)

    @pytest.mark.asyncio
    async def test_failed_change_increments_rate_limit(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
    ):
        """Failed password change should increment rate limit counter."""
        mock_user_service.change_password = AsyncMock(
            side_effect=InvalidCredentialsError("Current password is incorrect")
        )

        with patch(
            "backend.api.user_management.users.PasswordChangeRateLimiter"
        ) as MockLimiter:
            mock_limiter = AsyncMock()
            mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
            mock_limiter.record_attempt = AsyncMock()
            MockLimiter.return_value = mock_limiter

            from fastapi import HTTPException
            from user_management.schemas import PasswordChange

            from backend.api.user_management.users import change_password

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await change_password(
                    user_id, pwd_change, mock_user_service, mock_current_user
                )

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            mock_limiter.record_attempt.assert_called_once_with(user_id, success=False)


# ---------------------------------------------------------------------------
# Test: Password Change Responses
# ---------------------------------------------------------------------------


class TestPasswordChangeResponses:
    """Tests for password change response handling."""

    @pytest.mark.asyncio
    async def test_user_not_found_returns_404(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
    ):
        """Should return 404 when user is not found."""
        mock_user_service.change_password = AsyncMock(
            side_effect=UserNotFoundError(f"User {user_id} not found")
        )

        with patch(
            "backend.api.user_management.users.PasswordChangeRateLimiter"
        ) as MockLimiter:
            mock_limiter = AsyncMock()
            mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
            MockLimiter.return_value = mock_limiter

            from fastapi import HTTPException
            from user_management.schemas import PasswordChange

            from backend.api.user_management.users import change_password

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await change_password(
                    user_id, pwd_change, mock_user_service, mock_current_user
                )

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_invalid_credentials_returns_401(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
    ):
        """Should return 401 when current password is incorrect."""
        mock_user_service.change_password = AsyncMock(
            side_effect=InvalidCredentialsError("Current password is incorrect")
        )

        with patch(
            "backend.api.user_management.users.PasswordChangeRateLimiter"
        ) as MockLimiter:
            mock_limiter = AsyncMock()
            mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
            mock_limiter.record_attempt = AsyncMock()
            MockLimiter.return_value = mock_limiter

            from fastapi import HTTPException
            from user_management.schemas import PasswordChange

            from backend.api.user_management.users import change_password

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await change_password(
                    user_id, pwd_change, mock_user_service, mock_current_user
                )

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Current password is incorrect" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_successful_change_returns_success_message(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
    ):
        """Should return success message on successful password change."""
        with patch(
            "backend.api.user_management.users.PasswordChangeRateLimiter"
        ) as MockLimiter:
            mock_limiter = AsyncMock()
            mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
            mock_limiter.record_attempt = AsyncMock()
            MockLimiter.return_value = mock_limiter

            from user_management.schemas import PasswordChange

            from backend.api.user_management.users import change_password

            pwd_change = PasswordChange(**password_data)
            response = await change_password(
                user_id, pwd_change, mock_user_service, mock_current_user
            )

            assert response.success is True
            assert response.message == "Password changed successfully"
