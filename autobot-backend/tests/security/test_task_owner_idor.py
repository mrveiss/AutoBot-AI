# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Security tests for task-owner IDOR fix on /steer and /answer endpoints (#10553).

Acceptance criteria:
  - User A steers a task; user B steering the same task → 403.
  - User A answers a question; user B answering the same task's question → 403.
  - Admin user can steer/answer any task (bypass).
  - First caller establishes ownership (SET NX pattern).
  - verify_task_owner degrades gracefully on Redis outage (fail-open).
"""

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# task_owner unit tests (no FastAPI needed)
# ---------------------------------------------------------------------------


@pytest.fixture
def redis_store():
    """In-memory dict simulating Redis for task_owner tests."""
    return {}


async def _fake_redis_get(key, *, store):
    val = store.get(key)
    return val.encode() if isinstance(val, str) else val


async def _fake_redis_set(key, value, expire=None, *, store):
    store[key] = value
    return True


async def _fake_redis_delete(key, *, store):
    store.pop(key, None)
    return 1


def _patch_redis(store):
    return (
        patch("services.task_owner.redis_get", new=lambda key: _fake_redis_get(key, store=store)),
        patch(
            "services.task_owner.redis_set",
            new=lambda key, val, expire=None: _fake_redis_set(key, val, expire=expire, store=store),
        ),
        patch("services.task_owner.redis_delete", new=lambda key: _fake_redis_delete(key, store=store)),
    )


class TestVerifyTaskOwner:
    @pytest.mark.asyncio
    async def test_first_caller_becomes_owner(self, redis_store):
        from services.task_owner import verify_task_owner

        with _patch_redis(redis_store)[0], _patch_redis(redis_store)[1], _patch_redis(redis_store)[2]:
            result = await verify_task_owner("task-abc", "user-A")
        assert result is True

    @pytest.mark.asyncio
    async def test_owner_can_steer_again(self, redis_store):
        from services.task_owner import verify_task_owner

        p0, p1, p2 = _patch_redis(redis_store)
        with p0, p1, p2:
            await verify_task_owner("task-abc", "user-A")  # registers
            result = await verify_task_owner("task-abc", "user-A")
        assert result is True

    @pytest.mark.asyncio
    async def test_different_user_is_rejected(self, redis_store):
        from services.task_owner import verify_task_owner

        p0, p1, p2 = _patch_redis(redis_store)
        with p0, p1, p2:
            await verify_task_owner("task-abc", "user-A")  # A registers
            result = await verify_task_owner("task-abc", "user-B")
        assert result is False

    @pytest.mark.asyncio
    async def test_admin_bypasses_ownership(self, redis_store):
        from services.task_owner import verify_task_owner

        p0, p1, p2 = _patch_redis(redis_store)
        with p0, p1, p2:
            await verify_task_owner("task-abc", "user-A")  # A registers
            result = await verify_task_owner("task-abc", "user-B", user_role="admin")
        assert result is True

    @pytest.mark.asyncio
    async def test_redis_outage_fails_open(self):
        from services.task_owner import verify_task_owner

        async def _boom(key):
            raise ConnectionError("Redis down")

        with patch("services.task_owner.redis_get", new=_boom):
            result = await verify_task_owner("task-xyz", "user-A")
        assert result is True  # fail-open: task interaction must not block


class TestRegisterTaskOwner:
    @pytest.mark.asyncio
    async def test_set_nx_first_writer_wins(self, redis_store):
        from services.task_owner import register_task_owner

        p0, p1, p2 = _patch_redis(redis_store)
        with p0, p1, p2:
            r1 = await register_task_owner("task-new", "user-A")
            r2 = await register_task_owner("task-new", "user-B")  # loses race

        assert r1 is True
        assert r2 is False


# ---------------------------------------------------------------------------
# Integration-style tests for the endpoint ownership gate
# (no TestClient — patch verify_task_owner to avoid needing full FastAPI app)
# ---------------------------------------------------------------------------


class TestEndpointOwnershipGuard:
    """Test the ownership guard logic that is applied inside steer/answer endpoints.

    The guard in each endpoint is:
        user_id = current_user.get("user_id") or ...
        if not await verify_task_owner(task_id, user_id, user_role):
            raise HTTPException(403, ...)

    We test verify_task_owner directly (same call the endpoints make) to verify
    that user B calling on user A's task is rejected and admin is allowed.
    """

    @pytest.mark.asyncio
    async def test_user_b_on_user_a_task_returns_false(self, redis_store):
        """verify_task_owner returns False for the wrong user — endpoint would 403."""
        from services.task_owner import verify_task_owner

        p0, p1, p2 = _patch_redis(redis_store)
        with p0, p1, p2:
            await verify_task_owner("task-a", "user-A")  # A registers
            result = await verify_task_owner("task-a", "user-B", user_role="user")
        assert result is False, "User B must be rejected from user A's task"

    @pytest.mark.asyncio
    async def test_admin_on_any_task_returns_true(self, redis_store):
        """verify_task_owner returns True for admin regardless of registered owner."""
        from services.task_owner import verify_task_owner

        p0, p1, p2 = _patch_redis(redis_store)
        with p0, p1, p2:
            await verify_task_owner("task-a", "user-A")  # A registers
            result = await verify_task_owner("task-a", "user-B", user_role="admin")
        assert result is True, "Admin must be able to steer any task"

    @pytest.mark.asyncio
    async def test_owner_on_own_task_returns_true(self, redis_store):
        """verify_task_owner returns True for the task's registered owner."""
        from services.task_owner import verify_task_owner

        p0, p1, p2 = _patch_redis(redis_store)
        with p0, p1, p2:
            await verify_task_owner("task-b", "user-A")  # A registers
            result = await verify_task_owner("task-b", "user-A", user_role="user")
        assert result is True
