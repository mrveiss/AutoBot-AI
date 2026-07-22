# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for api.desktop_control_lock (Issue #12002, #11506 T1).

Covers: acquire/release/is_human_active/get_lock_owner round-trip via a
fake Redis client, owner-mismatch release denial, and fail-safe behaviour
(mute agent) when Redis is unavailable.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.desktop_control_lock import (
    DEFAULT_DESKTOP_SESSION_ID,
    acquire_human_control,
    get_control_lock_state,
    get_lock_owner,
    is_human_active,
    release_human_control,
)


class FakeAsyncRedis:
    """Minimal in-memory async Redis stand-in for control-lock round-trips."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self._store[key] = value
        return True

    async def delete(self, key: str):
        self._store.pop(key, None)
        return 1


@pytest.fixture
def fake_redis():
    return FakeAsyncRedis()


def _patch_redis(fake_redis):
    return patch(
        "api.desktop_control_lock.get_redis_client",
        new=AsyncMock(return_value=fake_redis),
    )


class TestAcquireRelease:
    @pytest.mark.asyncio
    async def test_acquire_sets_lock_and_owner(self, fake_redis):
        with _patch_redis(fake_redis):
            result = await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

        assert result["success"] is True
        assert result["owner"] == "alice"
        assert result["human_active"] is True

    @pytest.mark.asyncio
    async def test_is_human_active_true_after_acquire(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            assert await is_human_active(DEFAULT_DESKTOP_SESSION_ID) is True
            assert await get_lock_owner(DEFAULT_DESKTOP_SESSION_ID) == "alice"

    @pytest.mark.asyncio
    async def test_is_human_active_false_when_no_lock(self, fake_redis):
        with _patch_redis(fake_redis):
            assert await is_human_active("no-such-session") is False
            assert await get_lock_owner("no-such-session") is None

    @pytest.mark.asyncio
    async def test_release_by_owner_succeeds(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            result = await release_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

            assert result["success"] is True
            assert result["human_active"] is False
            assert await is_human_active(DEFAULT_DESKTOP_SESSION_ID) is False

    @pytest.mark.asyncio
    async def test_release_by_non_owner_denied(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            result = await release_human_control(DEFAULT_DESKTOP_SESSION_ID, "bob")

            assert result["success"] is False
            assert result["owner"] == "alice"
            # Lock must still be held -- non-owner release is a no-op.
            assert await is_human_active(DEFAULT_DESKTOP_SESSION_ID) is True

    @pytest.mark.asyncio
    async def test_release_with_no_lock_is_a_success_noop(self, fake_redis):
        with _patch_redis(fake_redis):
            result = await release_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

            assert result["success"] is True
            assert result["human_active"] is False

    @pytest.mark.asyncio
    async def test_reacquire_by_different_owner_overwrites(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "bob")

            assert await get_lock_owner(DEFAULT_DESKTOP_SESSION_ID) == "bob"


class TestControlLockState:
    @pytest.mark.asyncio
    async def test_state_reflects_current_owner(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            state = await get_control_lock_state(DEFAULT_DESKTOP_SESSION_ID)

        assert state["human_active"] is True
        assert state["owner"] == "alice"
        assert state["redis_available"] is True
        assert state["acquired_at"] is not None

    @pytest.mark.asyncio
    async def test_state_when_unheld(self, fake_redis):
        with _patch_redis(fake_redis):
            state = await get_control_lock_state("empty-session")

        assert state["human_active"] is False
        assert state["owner"] is None


class TestRedisUnavailableFailSafe:
    """Redis outages must fail SAFE: mute the agent, never silently unmute it."""

    @pytest.mark.asyncio
    async def test_is_human_active_fails_safe_when_redis_down(self):
        with patch(
            "api.desktop_control_lock.get_redis_client",
            new=AsyncMock(return_value=None),
        ):
            assert await is_human_active(DEFAULT_DESKTOP_SESSION_ID) is True

    @pytest.mark.asyncio
    async def test_acquire_fails_cleanly_when_redis_down(self):
        with patch(
            "api.desktop_control_lock.get_redis_client",
            new=AsyncMock(return_value=None),
        ):
            result = await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_release_fails_cleanly_when_redis_down(self):
        with patch(
            "api.desktop_control_lock.get_redis_client",
            new=AsyncMock(return_value=None),
        ):
            result = await release_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

        assert result["success"] is False
        assert result["human_active"] is True

    @pytest.mark.asyncio
    async def test_get_lock_owner_none_when_redis_down(self):
        with patch(
            "api.desktop_control_lock.get_redis_client",
            new=AsyncMock(return_value=None),
        ):
            assert await get_lock_owner(DEFAULT_DESKTOP_SESSION_ID) is None


class TestRedisKeyShape:
    @pytest.mark.asyncio
    async def test_lock_stored_as_json_with_owner_and_timestamp(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

        raw = fake_redis._store[f"autobot:desktop:control_lock:{DEFAULT_DESKTOP_SESSION_ID}"]
        record = json.loads(raw)
        assert record["owner"] == "alice"
        assert "acquired_at" in record
