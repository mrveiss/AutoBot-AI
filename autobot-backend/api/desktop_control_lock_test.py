# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for api.desktop_control_lock (Issue #12002, #11506 T1).

Covers: acquire/release/is_human_active/get_lock_owner round-trip via a
fake Redis client, owner-mismatch release denial, fail-safe behaviour (mute
agent) when Redis is unavailable, the atomic Lua-based release (no
GET-then-DELETE TOCTOU window), and owner-aware muting (is_actuation_muted).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.desktop_control_lock import (
    DEFAULT_DESKTOP_SESSION_ID,
    acquire_human_control,
    get_control_lock_state,
    get_lock_owner,
    is_actuation_muted,
    is_human_active,
    release_human_control,
)


class FakeAsyncRedis:
    """Minimal in-memory async Redis stand-in for control-lock round-trips.

    ``eval`` mirrors the real Redis Lua script's atomic
    compare-owner-and-delete semantics: in real Redis this executes as a
    single uninterruptible server-side operation (no other client command
    can interleave mid-script), so this fake performs the check+delete as
    one synchronous Python step with no ``await`` in between -- the same
    "no TOCTOU window" guarantee the real EVAL call provides.
    """

    def __init__(self):
        self._store: dict[str, str] = {}
        self.calls: list[str] = []

    async def get(self, key: str):
        self.calls.append("get")
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.calls.append("set")
        self._store[key] = value
        return True

    async def delete(self, key: str):
        self.calls.append("delete")
        self._store.pop(key, None)
        return 1

    async def eval(self, script: str, numkeys: int, *keys_and_args):
        # NOTE: this is the redis-py client's EVAL RPC method (matching
        # redis.asyncio.Redis.eval, which sends the Lua `script` string to
        # the Redis SERVER to run there) -- not Python's builtin eval(). No
        # arbitrary code from `script` is ever executed in this process;
        # this fake just re-implements the script's fixed compare-and-delete
        # logic in Python for testing, ignoring the `script` text itself.
        self.calls.append("eval")
        key = keys_and_args[0]
        owner = keys_and_args[1]
        raw = self._store.get(key)
        if raw is None:
            return "NONE"
        data = json.loads(raw)
        if data.get("owner") != owner:
            return raw
        del self._store[key]
        return "OK"


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


class TestAtomicReleaseRace:
    """Regression coverage for the GET-then-DELETE TOCTOU race (#12002 review).

    Interleaving: owner A releases (reads owner=A, passes the check) while
    owner B's takeover lands in the window between A's read and A's delete
    -- A's stale DELETE must NOT remove B's freshly-acquired lock.
    """

    @pytest.mark.asyncio
    async def test_stale_release_does_not_delete_a_newer_owners_lock(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            # B's takeover interleaves before A's (stale) release reaches Redis.
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "bob")

            result = await release_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

            assert result["success"] is False
            assert result["owner"] == "bob"
            # B's lock must survive A's stale release attempt.
            assert await is_human_active(DEFAULT_DESKTOP_SESSION_ID) is True
            assert await get_lock_owner(DEFAULT_DESKTOP_SESSION_ID) == "bob"

    @pytest.mark.asyncio
    async def test_release_is_a_single_atomic_round_trip(self, fake_redis):
        """No separate GET-then-DELETE pair -- exactly one EVAL call, closing
        the TOCTOU window structurally (there is nothing to interleave with)."""
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            fake_redis.calls.clear()

            await release_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")

        assert fake_redis.calls == ["eval"]


class TestOwnerAwareMuting:
    """is_actuation_muted: unconditional for the agent (caller=None), but
    the lock owner's own REST toolbar calls must not mute themselves."""

    @pytest.mark.asyncio
    async def test_agent_muted_regardless_of_who_holds_lock(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            assert await is_actuation_muted(DEFAULT_DESKTOP_SESSION_ID) is True
            assert await is_actuation_muted(DEFAULT_DESKTOP_SESSION_ID, caller=None) is True

    @pytest.mark.asyncio
    async def test_lock_owner_not_muted_for_their_own_toolbar(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            assert await is_actuation_muted(DEFAULT_DESKTOP_SESSION_ID, caller="alice") is False

    @pytest.mark.asyncio
    async def test_non_owner_human_is_muted(self, fake_redis):
        with _patch_redis(fake_redis):
            await acquire_human_control(DEFAULT_DESKTOP_SESSION_ID, "alice")
            assert await is_actuation_muted(DEFAULT_DESKTOP_SESSION_ID, caller="bob") is True

    @pytest.mark.asyncio
    async def test_unmuted_for_everyone_when_no_lock_held(self, fake_redis):
        with _patch_redis(fake_redis):
            assert await is_actuation_muted(DEFAULT_DESKTOP_SESSION_ID) is False
            assert await is_actuation_muted(DEFAULT_DESKTOP_SESSION_ID, caller="alice") is False

    @pytest.mark.asyncio
    async def test_muted_fails_safe_when_redis_down(self):
        with patch("api.desktop_control_lock.get_redis_client", new=AsyncMock(return_value=None)):
            assert await is_actuation_muted(DEFAULT_DESKTOP_SESSION_ID, caller="alice") is True


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
