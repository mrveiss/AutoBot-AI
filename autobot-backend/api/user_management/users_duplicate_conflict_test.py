# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for duplicate-user 409 responses on the users API.

DuplicateUserError used to be swallowed into a 409 whose detail said
"Internal server error" — a status/body mismatch, since a 409 is a client
conflict, not a server fault. Issue #15736.
"""

import uuid

import pytest
from fastapi import HTTPException, status

from user_management.schemas import UserCreate, UserUpdate
from user_management.services.user_service import DuplicateUserError


@pytest.fixture
def user_id():
    """Generate test user ID."""
    return uuid.uuid4()


class TestCreateUserDuplicateConflict:
    """create_user must not claim a server fault for a 409 conflict."""

    @pytest.mark.asyncio
    async def test_duplicate_email_returns_409_naming_the_field(self):
        """409 detail names the conflicting field, never 'Internal server error'."""
        from api.user_management.users import create_user

        class _Service:
            async def create_user(self, **kwargs):
                raise DuplicateUserError("User with email 'a@example.com' already exists", field="email")

        user_data = UserCreate(email="a@example.com", username="someuser")

        with pytest.raises(HTTPException) as exc_info:
            await create_user(user_data, _Service())

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "Internal server error" not in str(exc_info.value.detail)
        assert "email" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_duplicate_conflict_does_not_echo_submitted_value(self):
        """Not admin-gated (#15736): detail names the field, not the submitted value."""
        from api.user_management.users import create_user

        class _Service:
            async def create_user(self, **kwargs):
                raise DuplicateUserError("Username 'takenname' already exists", field="username")

        user_data = UserCreate(email="b@example.com", username="takenname")

        with pytest.raises(HTTPException) as exc_info:
            await create_user(user_data, _Service())

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "takenname" not in str(exc_info.value.detail)


class TestUpdateUserDuplicateConflict:
    """update_user must not claim a server fault for a 409 conflict."""

    @pytest.mark.asyncio
    async def test_duplicate_username_returns_409_naming_the_field(self, user_id):
        """409 detail names the conflicting field, never 'Internal server error'."""
        from api.user_management.users import update_user

        class _Service:
            async def update_user(self, **kwargs):
                raise DuplicateUserError("Username 'takenname' already in use", field="username")

        user_data = UserUpdate(username="takenname")

        with pytest.raises(HTTPException) as exc_info:
            await update_user(user_id, user_data, _Service())

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "Internal server error" not in str(exc_info.value.detail)
        assert "username" in str(exc_info.value.detail)
        assert "takenname" not in str(exc_info.value.detail)
