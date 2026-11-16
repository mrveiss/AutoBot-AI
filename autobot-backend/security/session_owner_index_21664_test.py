# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The owner index: a Redis error is an error, and an empty set is a cache miss (#21664).

``SessionOwnershipValidator.get_user_sessions`` used to swallow a Redis error and return ``[]``,
which the list route answered with ``intentional_empty`` -- telling the UI to wipe its local
sessions on a Redis blip. ``owned_session_ids`` reads an empty set as "not cached" and rebuilds
it from the session files, because Redis is a TTL cache and the file's owner is the record of
truth (THREAT_MODEL.md section 2).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from security.session_owner_errors import SessionOwnerUnreadable
from security.session_owner_index import owned_session_ids
from security.session_ownership import SessionOwnershipValidator


def _redis(members=None, error=None):
    redis = MagicMock()
    redis.smembers = AsyncMock(return_value=members or set(), side_effect=error)
    return redis


@pytest.mark.asyncio
async def test_get_user_sessions_lets_a_redis_error_through():
    validator = SessionOwnershipValidator(_redis(error=ConnectionError("redis down")))
    with pytest.raises(ConnectionError):
        await validator.get_user_sessions("alice")


@pytest.mark.asyncio
async def test_get_user_sessions_decodes_members():
    validator = SessionOwnershipValidator(_redis(members={b"s-1", "s-2"}))
    assert sorted(await validator.get_user_sessions("alice")) == ["s-1", "s-2"]


def _validator(cached):
    v = MagicMock()
    v.get_user_sessions = AsyncMock(return_value=cached)
    v.set_session_owner = AsyncMock(return_value=True)
    return v


@pytest.mark.asyncio
async def test_a_cached_index_is_used_without_reading_the_files():
    read_owner = AsyncMock()
    assert await owned_session_ids(_validator(["s-1"]), "alice", ["s-1", "s-2"], read_owner) == {"s-1"}
    read_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_empty_index_is_rebuilt_from_the_durable_owner_and_recached():
    validator = _validator([])
    disk = {"s-1": "alice", "s-2": "bob", "s-3": None}
    read_owner = AsyncMock(side_effect=lambda sid: disk[sid])
    assert await owned_session_ids(validator, "alice", list(disk), read_owner) == {"s-1"}
    validator.set_session_owner.assert_awaited_once_with("s-1", "alice")


@pytest.mark.asyncio
async def test_an_unreadable_session_file_is_left_out_not_claimed():
    validator = _validator([])

    async def read_owner(sid):
        if sid == "s-bad":
            raise SessionOwnerUnreadable(sid)
        return "alice"

    assert await owned_session_ids(validator, "alice", ["s-bad", "s-1"], read_owner) == {"s-1"}


@pytest.mark.asyncio
async def test_an_index_read_error_propagates():
    validator = _validator([])
    validator.get_user_sessions = AsyncMock(side_effect=ConnectionError("redis down"))
    with pytest.raises(ConnectionError):
        await owned_session_ids(validator, "alice", ["s-1"], AsyncMock())
