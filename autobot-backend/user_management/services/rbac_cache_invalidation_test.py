# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
RBAC cache invalidation tests (GH#7609).

Verifies that assign_role and revoke_role correctly invalidate the Redis L2
permission cache (``rbac:perm:{user_id}``) and the L1 in-process dict on
the calling worker.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Pre-import TerminalActivityModel so SQLAlchemy can resolve the string-based
# relationship on User.terminal_activities before UserRole mapper initialises.
import models.activities  # noqa: F401
from user_management.services.user_service import UserService

_REDIS_KEY_PREFIX = "rbac:perm:"
_PUBSUB_CHANNEL = "autobot:rbac:invalidate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_execute_result(scalar_return=None) -> MagicMock:
    """Return a MagicMock that mimics SQLAlchemy execute() result.

    ``scalar_one_or_none`` is a regular (sync) call on the result object,
    so we return a plain MagicMock with an explicit return value to avoid
    the auto-spec issue where child mocks become AsyncMock.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_return
    return result


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.delete = AsyncMock()
    redis.publish = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = AsyncMock()
    # Return a plain MagicMock for execute() results so child attributes
    # (scalar_one_or_none, etc.) don't auto-inherit AsyncMock behaviour.
    session.execute = AsyncMock(return_value=_mock_execute_result(scalar_return=None))
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    # Empty info dict → no _post_commit_cbs key → clear_cache fires immediately (fallback path).
    # Integration tests with a real session exercise the post-commit path (GH#7605).
    session.info = {}
    return session


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.org_id = uuid.uuid4()
    context.user_id = uuid.uuid4()
    return context


@pytest.fixture
def user_service(mock_session, mock_context):
    return UserService(session=mock_session, context=mock_context)


@pytest.fixture
def sample_ids():
    return {"user_id": uuid.uuid4(), "role_id": uuid.uuid4()}


# ---------------------------------------------------------------------------
# assign_role → cache invalidation
# ---------------------------------------------------------------------------


class TestAssignRoleCacheInvalidation:
    """GH#7609 — assign_role must invalidate the RBAC permission cache."""

    @pytest.mark.asyncio
    async def test_assign_role_deletes_redis_key(self, user_service, mock_session, sample_ids):
        """Redis L2 key ``rbac:perm:{user_id}`` is deleted after role assignment."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        # No existing role → assignment proceeds
        mock_session.execute.return_value = _mock_execute_result(scalar_return=None)

        redis = _make_redis()

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            result = await user_service.assign_role(user_id, role_id)

        assert result is True
        redis.delete.assert_awaited_once_with(f"{_REDIS_KEY_PREFIX}{user_id}")

    @pytest.mark.asyncio
    async def test_assign_role_publishes_invalidation_event(self, user_service, mock_session, sample_ids):
        """A pub/sub message is broadcast to invalidate L1 caches on other workers."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        mock_session.execute.return_value = _mock_execute_result(scalar_return=None)

        redis = _make_redis()

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            await user_service.assign_role(user_id, role_id)

        redis.publish.assert_awaited_once()
        channel, payload = redis.publish.call_args.args
        assert channel == _PUBSUB_CHANNEL
        assert str(user_id) in payload

    @pytest.mark.asyncio
    async def test_assign_role_already_assigned_skips_cache_clear(self, user_service, mock_session, sample_ids):
        """When the role is already assigned, no cache invalidation occurs."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        # Simulate existing assignment
        mock_session.execute.return_value = _mock_execute_result(scalar_return=MagicMock())

        redis = _make_redis()

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            result = await user_service.assign_role(user_id, role_id)

        assert result is False
        redis.delete.assert_not_awaited()
        redis.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_assign_role_clears_l1_cache_for_user(self, user_service, mock_session, sample_ids):
        """L1 in-process cache entry is removed for the specific user."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        mock_session.execute.return_value = _mock_execute_result(scalar_return=None)

        redis = _make_redis()

        from user_management.middleware.rbac_middleware import _permission_cache

        _permission_cache[str(user_id)] = ({"some:perm"}, 1234567890.0)

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            await user_service.assign_role(user_id, role_id)

        assert str(user_id) not in _permission_cache


# ---------------------------------------------------------------------------
# revoke_role → cache invalidation
# ---------------------------------------------------------------------------


class TestRevokeRoleCacheInvalidation:
    """GH#7609 — revoke_role must invalidate the RBAC permission cache."""

    @pytest.mark.asyncio
    async def test_revoke_role_deletes_redis_key(self, user_service, mock_session, sample_ids):
        """Redis L2 key ``rbac:perm:{user_id}`` is deleted after role revocation."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        existing_role = MagicMock()
        mock_session.execute.return_value = _mock_execute_result(scalar_return=existing_role)

        redis = _make_redis()

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            result = await user_service.revoke_role(user_id, role_id)

        assert result is True
        redis.delete.assert_awaited_once_with(f"{_REDIS_KEY_PREFIX}{user_id}")

    @pytest.mark.asyncio
    async def test_revoke_role_publishes_invalidation_event(self, user_service, mock_session, sample_ids):
        """A pub/sub message is broadcast to invalidate L1 caches on other workers."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        mock_session.execute.return_value = _mock_execute_result(scalar_return=MagicMock())

        redis = _make_redis()

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            await user_service.revoke_role(user_id, role_id)

        redis.publish.assert_awaited_once()
        channel, payload = redis.publish.call_args.args
        assert channel == _PUBSUB_CHANNEL
        assert str(user_id) in payload

    @pytest.mark.asyncio
    async def test_revoke_role_not_found_skips_cache_clear(self, user_service, mock_session, sample_ids):
        """When the role is not assigned, no cache invalidation occurs."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        mock_session.execute.return_value = _mock_execute_result(scalar_return=None)

        redis = _make_redis()

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            result = await user_service.revoke_role(user_id, role_id)

        assert result is False
        redis.delete.assert_not_awaited()
        redis.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revoke_role_clears_l1_cache_for_user(self, user_service, mock_session, sample_ids):
        """L1 in-process cache entry is removed for the specific user."""
        user_id = sample_ids["user_id"]
        role_id = sample_ids["role_id"]

        mock_session.execute.return_value = _mock_execute_result(scalar_return=MagicMock())

        redis = _make_redis()

        from user_management.middleware.rbac_middleware import _permission_cache

        _permission_cache[str(user_id)] = ({"another:perm"}, 1234567890.0)

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            await user_service.revoke_role(user_id, role_id)

        assert str(user_id) not in _permission_cache


# ---------------------------------------------------------------------------
# Concurrent assign/revoke — no race condition
# ---------------------------------------------------------------------------


class TestConcurrentRoleMutations:
    """GH#7609 — concurrent assign/revoke do not corrupt cache state."""

    @pytest.mark.asyncio
    async def test_concurrent_assign_and_revoke_both_invalidate(self, user_service, mock_session, sample_ids):
        """Parallel assign and revoke each trigger independent cache clears."""
        user_id = sample_ids["user_id"]
        role_id_a = uuid.uuid4()
        role_id_b = uuid.uuid4()

        # assign: no existing; revoke: existing role found
        side_effects = [
            _mock_execute_result(scalar_return=None),  # assign call
            _mock_execute_result(scalar_return=MagicMock()),  # revoke call
        ]
        mock_session.execute.side_effect = side_effects

        redis = _make_redis()

        with (
            patch(
                "user_management.middleware.rbac_middleware.get_async_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch.object(user_service, "_audit_log", new_callable=AsyncMock),
        ):
            assign_task = asyncio.create_task(user_service.assign_role(user_id, role_id_a))
            revoke_task = asyncio.create_task(user_service.revoke_role(user_id, role_id_b))
            results = await asyncio.gather(assign_task, revoke_task)

        assert True in results  # At least one op returned True
        # Two separate delete + publish calls, one per operation
        assert redis.delete.await_count == 2
        assert redis.publish.await_count == 2
        for c in redis.delete.call_args_list:
            assert c == call(f"{_REDIS_KEY_PREFIX}{user_id}")
