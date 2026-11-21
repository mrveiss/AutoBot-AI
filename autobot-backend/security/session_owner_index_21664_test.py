# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The owner index: a Redis error is an error, and the set is trusted only behind its marker (#21664).

``SessionOwnershipValidator.get_user_sessions`` used to swallow a Redis error and return ``[]``,
which the list route answered with ``intentional_empty``. ``owned_session_ids`` reads the set only
while ``user_chat_sessions_complete:<user>`` exists: after the set expires, one new ``sadd`` would
otherwise make it look complete with a single member. Without the marker it rebuilds from the
session files (THREAT_MODEL.md section 2) and writes the marker, also when nothing is owned.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.ssot_constants import TTL_30_DAYS
from security.session_owner_errors import SessionOwnerUnreadable
from security.session_owner_index import (
    OWNER_INDEX_COMPLETE_TTL,
    complete_key,
    index_owner_or_unmark,
    owned_session_ids,
)
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


class _Store:
    """Just the keys this module touches: the user's set (``sadd``) and the marker."""

    def __init__(self, members=(), marked=False):
        self.members, self.keys = set(members), {}
        if marked:
            self.keys[complete_key("alice")] = "1"

    async def exists(self, key):
        return int(key in self.keys)

    async def set(self, key, value, ex=None):
        self.keys[key] = (value, ex)

    async def delete(self, key):
        self.keys.pop(key, None)


def _validator(store, recache_ok=True):
    v = MagicMock()
    v.redis = store
    v.get_user_sessions = AsyncMock(side_effect=lambda username: list(store.members))

    async def set_session_owner(session_id, username, **context):
        if recache_ok:
            store.members.add(session_id)
        return recache_ok

    v.set_session_owner = AsyncMock(side_effect=set_session_owner)
    return v


def _disk(owners):
    return AsyncMock(side_effect=lambda sid: owners[sid])


@pytest.mark.asyncio
async def test_a_marked_index_is_used_without_reading_the_files():
    read_owner = AsyncMock()
    validator = _validator(_Store(members={"s-1"}, marked=True))
    assert await owned_session_ids(validator, "alice", ["s-1", "s-2"], read_owner) == {"s-1"}
    read_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_expired_set_with_one_new_sadd_still_lists_the_older_owned_session():
    """The set expired, then one new session was added: ``{s-new}`` alone is not complete."""
    validator = _validator(_Store(members={"s-new"}))
    read_owner = _disk({"s-old": "alice", "s-new": "alice", "s-bob": "bob"})
    assert await owned_session_ids(validator, "alice", ["s-old", "s-new", "s-bob"], read_owner) == {"s-old", "s-new"}


@pytest.mark.asyncio
async def test_a_user_who_owns_nothing_reads_no_file_on_the_second_call():
    store = _Store()
    read_owner = _disk({"s-1": "bob", "s-2": "bob"})
    assert await owned_session_ids(_validator(store), "alice", ["s-1", "s-2"], read_owner) == set()
    assert read_owner.await_count == 2
    assert await owned_session_ids(_validator(store), "alice", ["s-1", "s-2"], read_owner) == set()
    assert read_owner.await_count == 2, "the empty result was not cached behind the marker"


@pytest.mark.asyncio
async def test_after_the_marker_expires_a_rebuild_runs_again():
    store = _Store()
    read_owner = _disk({"s-1": "alice"})
    await owned_session_ids(_validator(store), "alice", ["s-1"], read_owner)
    del store.keys[complete_key("alice")]  # the marker's TTL ran out
    await owned_session_ids(_validator(store), "alice", ["s-1"], read_owner)
    assert read_owner.await_count == 2


@pytest.mark.asyncio
async def test_the_marker_is_written_with_a_ttl_shorter_than_the_set():
    store = _Store()
    await owned_session_ids(_validator(store), "alice", [], _disk({}))
    assert store.keys[complete_key("alice")] == ("1", OWNER_INDEX_COMPLETE_TTL)
    assert 0 < OWNER_INDEX_COMPLETE_TTL < TTL_30_DAYS


@pytest.mark.asyncio
async def test_a_failed_recache_leaves_the_index_unmarked():
    store = _Store()
    owned = await owned_session_ids(_validator(store, recache_ok=False), "alice", ["s-1"], _disk({"s-1": "alice"}))
    assert owned == {"s-1"}
    assert complete_key("alice") not in store.keys


@pytest.mark.asyncio
async def test_an_unreadable_session_file_is_left_out_not_claimed():
    validator = _validator(_Store())

    async def read_owner(sid):
        if sid == "s-bad":
            raise SessionOwnerUnreadable(sid)
        return "alice"

    assert await owned_session_ids(validator, "alice", ["s-bad", "s-1"], read_owner) == {"s-1"}
    validator.set_session_owner.assert_awaited_once_with("s-1", "alice")


@pytest.mark.asyncio
async def test_an_index_read_error_propagates():
    validator = _validator(_Store(marked=True))
    validator.get_user_sessions = AsyncMock(side_effect=ConnectionError("redis down"))
    with pytest.raises(ConnectionError):
        await owned_session_ids(validator, "alice", ["s-1"], AsyncMock())


@pytest.mark.asyncio
async def test_a_rebuild_that_hits_an_unreadable_file_leaves_the_index_unmarked():
    store = _Store()

    async def read_owner(sid):
        if sid == "s-bad":
            raise SessionOwnerUnreadable(sid)
        return "alice"

    assert await owned_session_ids(_validator(store), "alice", ["s-bad", "s-1"], read_owner) == {"s-1"}
    assert complete_key("alice") not in store.keys


@pytest.mark.asyncio
async def test_a_successful_index_write_keeps_the_marked_set_complete():
    store = _Store(members={"s-old"}, marked=True)
    assert await index_owner_or_unmark(_validator(store), "s-new", "alice") is True
    assert await owned_session_ids(_validator(store), "alice", ["s-old", "s-new"], AsyncMock()) == {"s-old", "s-new"}


@pytest.mark.asyncio
async def test_a_failed_index_write_unmarks_and_the_next_list_rebuilds():
    store = _Store(members={"s-old"}, marked=True)
    assert await index_owner_or_unmark(_validator(store, recache_ok=False), "s-new", "alice") is False
    assert complete_key("alice") not in store.keys
    read_owner = _disk({"s-old": "alice", "s-new": "alice"})
    assert await owned_session_ids(_validator(store), "alice", ["s-old", "s-new"], read_owner) == {"s-old", "s-new"}
