# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for seed_default_admin (#10199).

Coverage:
- Seeds admin when none exists and password is configured.
- Idempotent: no second create when an is_platform_admin user exists.
- Idempotent: no second create when username already exists (non-admin).
- Skips without error when AUTOBOT_ADMIN_PASSWORD is not set.
- Created user has is_platform_admin=True.
- Admin role ID is looked up and passed to create_user.
- DuplicateUserError from UserService is swallowed (race guard).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from user_management.services.seed import seed_default_admin
from user_management.services.user_service import DuplicateUserError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(existing_admin=None, existing_role=None):
    """Return a mock AsyncSession whose execute() returns configured results."""
    session = AsyncMock()

    # We need execute to return different results for different queries.
    # seed_default_admin calls execute twice: once for _any_admin_exists (User
    # query) and once for _find_admin_role_id (Role query).
    execute_results = []

    # First call: _any_admin_exists  — scalar_one_or_none returns existing_admin
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = existing_admin
    execute_results.append(first_result)

    # Second call: _find_admin_role_id — scalar_one_or_none returns existing_role
    second_result = MagicMock()
    second_result.scalar_one_or_none.return_value = existing_role
    execute_results.append(second_result)

    session.execute = AsyncMock(side_effect=execute_results)
    return session


def _make_config(password="S3cur3P@ss!", username="admin"):
    cfg = MagicMock()
    cfg.auth.admin_password = password
    cfg.auth.admin_username = username
    return cfg


def _make_role():
    role = MagicMock()
    role.id = uuid.uuid4()
    return role


def _make_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_platform_admin = True
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_creates_admin_when_none_exists():
    """Creates admin when no admin user exists and password is configured."""
    admin_role = _make_role()
    created_user = _make_user()
    session = _make_session(existing_admin=None, existing_role=admin_role)

    with patch("user_management.services.seed.get_config", return_value=_make_config()):
        with patch("user_management.services.seed.UserService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.create_user = AsyncMock(return_value=created_user)

            await seed_default_admin(session)

    mock_svc.create_user.assert_awaited_once()
    call_kwargs = mock_svc.create_user.call_args.kwargs
    assert call_kwargs["is_platform_admin"] is True
    assert call_kwargs["password"] == "S3cur3P@ss!"
    assert call_kwargs["username"] == "admin"
    assert call_kwargs["role_ids"] == [admin_role.id]


@pytest.mark.asyncio
async def test_seed_idempotent_when_platform_admin_exists():
    """Skips creation when an is_platform_admin=True user already exists."""
    existing_admin = _make_user()
    session = _make_session(existing_admin=existing_admin)

    with patch("user_management.services.seed.get_config", return_value=_make_config()):
        with patch("user_management.services.seed.UserService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.create_user = AsyncMock()

            await seed_default_admin(session)

    mock_svc.create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_idempotent_when_username_exists():
    """Skips creation when the configured username already exists (non-admin duplicate)."""
    existing_user = MagicMock()
    existing_user.is_platform_admin = False
    session = _make_session(existing_admin=existing_user)

    with patch("user_management.services.seed.get_config", return_value=_make_config()):
        with patch("user_management.services.seed.UserService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.create_user = AsyncMock()

            await seed_default_admin(session)

    mock_svc.create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_skips_when_no_password_configured():
    """Returns without creating any user when AUTOBOT_ADMIN_PASSWORD is empty."""
    session = AsyncMock()

    with patch("user_management.services.seed.get_config", return_value=_make_config(password="")):
        with patch("user_management.services.seed.UserService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.create_user = AsyncMock()

            await seed_default_admin(session)

    # execute should not be called at all — we returned early
    session.execute.assert_not_called()
    mock_svc.create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_created_user_is_platform_admin():
    """Verifies is_platform_admin=True is passed to create_user."""
    admin_role = _make_role()
    created_user = _make_user()
    session = _make_session(existing_admin=None, existing_role=admin_role)

    with patch("user_management.services.seed.get_config", return_value=_make_config()):
        with patch("user_management.services.seed.UserService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.create_user = AsyncMock(return_value=created_user)

            await seed_default_admin(session)

    _, kwargs = mock_svc.create_user.call_args
    assert kwargs.get("is_platform_admin") is True


@pytest.mark.asyncio
async def test_seed_swallows_duplicate_user_error():
    """DuplicateUserError from UserService is caught, not propagated (race guard)."""
    admin_role = _make_role()
    session = _make_session(existing_admin=None, existing_role=admin_role)

    with patch("user_management.services.seed.get_config", return_value=_make_config()):
        with patch("user_management.services.seed.UserService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.create_user = AsyncMock(side_effect=DuplicateUserError("already exists"))

            # Must not raise
            await seed_default_admin(session)


@pytest.mark.asyncio
async def test_seed_without_admin_role_still_creates_user():
    """Creates user even when the 'admin' DB role is not found yet."""
    session = _make_session(existing_admin=None, existing_role=None)
    created_user = _make_user()

    with patch("user_management.services.seed.get_config", return_value=_make_config()):
        with patch("user_management.services.seed.UserService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.create_user = AsyncMock(return_value=created_user)

            await seed_default_admin(session)

    call_kwargs = mock_svc.create_user.call_args.kwargs
    # role_ids must be None when the role wasn't found
    assert call_kwargs["role_ids"] is None
    assert call_kwargs["is_platform_admin"] is True
