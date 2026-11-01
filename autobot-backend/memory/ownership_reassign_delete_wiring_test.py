# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``delete_user`` calls ``reassign_user_memory`` before it deletes the row (moved from ownership_reassign_test.py)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.db_session import POST_COMMIT_CALLBACKS


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.info = {POST_COMMIT_CALLBACKS: []}  # what async_session_scope seeds; delete_user queues on it
    return session


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.org_id = uuid.uuid4()
    context.user_id = uuid.uuid4()
    return context


@pytest.fixture
def user_service(mock_session, mock_context):
    from user_management.services.user_service import UserService

    return UserService(session=mock_session, context=mock_context)


@pytest.fixture
def sample_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_active = True
    return user


class TestDeleteUserReassignWiring:
    """delete_user calls reassign_user_memory before deleting the DB row."""

    @pytest.mark.asyncio
    async def test_reassign_to_calls_reassign_before_delete(
        self, user_service, sample_user, mock_session
    ):  # noqa: ARG002
        import sys

        new_owner = uuid.uuid4()
        fake_counts = {"verbatim": 3, "trajectory": 0, "working_memory": 1, "graph": 2}
        mock_reassign = AsyncMock(return_value=fake_counts)

        # The lazy import inside delete_user does:
        #   from memory.ownership_reassign import reassign_user_memory
        # Intercept via sys.modules so the imported name resolves to our mock.
        fake_module = MagicMock()
        fake_module.reassign_user_memory = mock_reassign

        with patch.dict(sys.modules, {"memory.ownership_reassign": fake_module}):
            with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
                with patch.object(user_service, "_audit_log", AsyncMock()):
                    result = await user_service.delete_user(
                        sample_user.id,
                        hard_delete=False,
                        reassign_to=new_owner,
                    )

        assert result is True
        mock_reassign.assert_called_once_with(str(sample_user.id), str(new_owner))

    @pytest.mark.asyncio
    async def test_no_reassign_to_skips_reassign(self, user_service, sample_user):
        """When reassign_to is None, reassign_user_memory is never called."""
        import sys

        mock_reassign = AsyncMock()
        fake_module = MagicMock()
        fake_module.reassign_user_memory = mock_reassign
        with patch.dict(sys.modules, {"memory.ownership_reassign": fake_module}):
            with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
                with patch.object(user_service, "_audit_log", AsyncMock()):
                    result = await user_service.delete_user(sample_user.id, hard_delete=False)

        assert result is True
        mock_reassign.assert_not_called()

    @pytest.mark.asyncio
    async def test_hard_delete_propagates_reassign_error(self, user_service, sample_user):
        """For hard_delete, if reassign raises the delete is aborted."""
        new_owner = uuid.uuid4()

        with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
            with patch.object(user_service, "_audit_log", AsyncMock()):
                broken_module = MagicMock()
                broken_module.reassign_user_memory = AsyncMock(side_effect=RuntimeError("store catastrophe"))
                with patch.dict("sys.modules", {"memory.ownership_reassign": broken_module}):
                    with pytest.raises(RuntimeError, match="store catastrophe"):
                        await user_service.delete_user(
                            sample_user.id,
                            hard_delete=True,
                            reassign_to=new_owner,
                        )

    @pytest.mark.asyncio
    async def test_soft_delete_continues_despite_reassign_error(self, user_service, sample_user):
        """For soft delete, a failing reassign logs a warning and proceeds."""
        new_owner = uuid.uuid4()

        with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
            with patch.object(user_service, "_audit_log", AsyncMock()):
                broken_module = MagicMock()
                broken_module.reassign_user_memory = AsyncMock(side_effect=RuntimeError("oops"))
                with patch.dict("sys.modules", {"memory.ownership_reassign": broken_module}):
                    result = await user_service.delete_user(
                        sample_user.id,
                        hard_delete=False,
                        reassign_to=new_owner,
                    )

        # Soft delete succeeded despite reassign error
        assert result is True
