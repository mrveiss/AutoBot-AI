# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Service Tests

Tests for user management operations including session invalidation on password change.
Issue #635.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.user_management.services.user_service import (
    InvalidCredentialsError,
    UserNotFoundError,
    UserService,
)


@pytest.fixture
def mock_session():
    """Mock SQLAlchemy async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_context():
    """Mock tenant context."""
    context = MagicMock()
    context.org_id = uuid.uuid4()
    context.user_id = uuid.uuid4()
    return context


@pytest.fixture
def user_service(mock_session, mock_context):
    """Create UserService instance with mocks."""
    return UserService(session=mock_session, context=mock_context)


@pytest.fixture
def sample_user():
    """Create a sample user for testing."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.password_hash = UserService.hash_password("OldPass123")
    user.is_active = True
    user.updated_at = datetime.now(timezone.utc)
    return user


@pytest.mark.asyncio
async def test_change_password_invalidates_sessions(user_service, sample_user):
    """Changing password invalidates other sessions. Issue #635."""
    current_token = "current.jwt.token"

    # Mock get_user to return sample_user
    with patch.object(
        user_service, "get_user", new_callable=AsyncMock
    ) as mock_get_user:
        mock_get_user.return_value = sample_user

        # Mock _audit_log
        with patch.object(
            user_service, "_audit_log", new_callable=AsyncMock
        ) as mock_audit:
            mock_audit.return_value = None

            # Mock SessionService
            with patch(
                "src.user_management.services.user_service.SessionService"
            ) as MockSession:
                mock_session_service = MockSession.return_value
                mock_session_service.invalidate_user_sessions = AsyncMock(
                    return_value=2
                )

                success = await user_service.change_password(
                    user_id=sample_user.id,
                    current_password="OldPass123",
                    new_password="NewPass456",
                    current_token=current_token,
                )

    assert success is True
    mock_session_service.invalidate_user_sessions.assert_called_once_with(
        user_id=sample_user.id, except_token=current_token
    )


@pytest.mark.asyncio
async def test_change_password_without_token_invalidates_all_sessions(
    user_service, sample_user
):
    """Changing password without token invalidates all sessions. Issue #635."""
    # Mock get_user to return sample_user
    with patch.object(
        user_service, "get_user", new_callable=AsyncMock
    ) as mock_get_user:
        mock_get_user.return_value = sample_user

        # Mock _audit_log
        with patch.object(
            user_service, "_audit_log", new_callable=AsyncMock
        ) as mock_audit:
            mock_audit.return_value = None

            # Mock SessionService
            with patch(
                "src.user_management.services.user_service.SessionService"
            ) as MockSession:
                mock_session_service = MockSession.return_value
                mock_session_service.invalidate_user_sessions = AsyncMock(
                    return_value=3
                )

                success = await user_service.change_password(
                    user_id=sample_user.id,
                    current_password="OldPass123",
                    new_password="NewPass456",
                )

    assert success is True
    mock_session_service.invalidate_user_sessions.assert_called_once_with(
        user_id=sample_user.id, except_token=None
    )


@pytest.mark.asyncio
async def test_change_password_user_not_found(user_service):
    """Changing password for non-existent user raises UserNotFoundError."""
    with patch.object(
        user_service, "get_user", new_callable=AsyncMock
    ) as mock_get_user:
        mock_get_user.return_value = None

        with pytest.raises(UserNotFoundError):
            await user_service.change_password(
                user_id=uuid.uuid4(),
                current_password="OldPass123",
                new_password="NewPass456",
            )


@pytest.mark.asyncio
async def test_change_password_wrong_current_password(user_service, sample_user):
    """Changing password with wrong current password raises InvalidCredentialsError."""
    with patch.object(
        user_service, "get_user", new_callable=AsyncMock
    ) as mock_get_user:
        mock_get_user.return_value = sample_user

        with pytest.raises(InvalidCredentialsError):
            await user_service.change_password(
                user_id=sample_user.id,
                current_password="WrongPassword",
                new_password="NewPass456",
            )
