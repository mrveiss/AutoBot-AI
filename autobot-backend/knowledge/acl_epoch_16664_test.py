# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The KB access-control epoch that partitions RAG caches over a revocation (#16664)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.acl_epoch import ACL_EPOCH_DATABASE, ACL_EPOCH_KEY, bump_acl_epoch, read_acl_epoch
from knowledge.ownership import KnowledgeOwnership
from testkit.fake_redis_pipeline import DualReply


def test_the_bump_sets_a_fresh_token_through_the_given_client():
    client = MagicMock()

    first, second = bump_acl_epoch(client), bump_acl_epoch(client)
    assert isinstance(first, str) and first != second
    client.set.assert_any_call(ACL_EPOCH_KEY, first)
    assert client.set.call_count == 2


def test_a_failed_bump_is_not_swallowed():
    """A revocation that did not invalidate the caches is a disclosure, so it must surface."""
    client = MagicMock()
    client.set.side_effect = ConnectionError("redis down")

    with pytest.raises(ConnectionError):
        bump_acl_epoch(client)


@pytest.mark.asyncio
@pytest.mark.parametrize("stored, expected", [(b"12", "12"), ("3", "3")])
async def test_the_epoch_decodes_what_is_stored(stored, expected):
    client = MagicMock(get=AsyncMock(return_value=stored), set=AsyncMock())

    with patch("knowledge.acl_epoch.get_async_redis_client", new=AsyncMock(return_value=client)) as getter:
        assert await read_acl_epoch() == expected

    getter.assert_awaited_once_with(database=ACL_EPOCH_DATABASE)
    client.get.assert_awaited_once_with(ACL_EPOCH_KEY)


@pytest.mark.asyncio
async def test_an_unavailable_or_failing_redis_reads_as_none_so_the_caches_are_skipped():
    with patch("knowledge.acl_epoch.get_async_redis_client", new=AsyncMock(return_value=None)):
        assert await read_acl_epoch() is None
    client = MagicMock(get=AsyncMock(side_effect=ConnectionError("down")))
    with patch("knowledge.acl_epoch.get_async_redis_client", new=AsyncMock(return_value=client)):
        assert await read_acl_epoch() is None
    # a key that stays missing after the NX mint is unreadable too
    client = MagicMock(get=AsyncMock(return_value=None), set=AsyncMock())
    with patch("knowledge.acl_epoch.get_async_redis_client", new=AsyncMock(return_value=client)):
        assert await read_acl_epoch() is None


class _Kv:
    """A knowledge-database stand-in for the ACL epoch key, with allkeys-lru eviction."""

    def __init__(self):
        self.data: dict[str, str] = {}

    def set(self, key, value, nx=False):
        if nx and key in self.data:
            return DualReply()
        self.data[key] = value
        return DualReply()

    async def get(self, key):
        return self.data[key].encode() if key in self.data else None


@pytest.mark.asyncio
async def test_an_evicted_epoch_never_revalidates_a_cache_entry_recorded_under_an_earlier_value():
    kv = _Kv()
    cache: dict[str, str] = {}
    seen = []
    with patch("knowledge.acl_epoch.get_async_redis_client", new=AsyncMock(return_value=kv)):
        for step in range(3):
            if step:
                kv.data.clear()  # eviction
            epoch = await read_acl_epoch()
            assert epoch not in (None, "0") and epoch not in seen
            seen.append(epoch)
            cache[epoch] = "stale-result"
            bumped = bump_acl_epoch(kv)
            assert bumped not in seen
            seen.append(bumped)
        kv.data.clear()
        assert await read_acl_epoch() not in cache, "an evicted epoch must not match any entry filled before"


def test_a_bump_after_an_eviction_does_not_reproduce_an_earlier_value():
    kv = _Kv()
    earlier = {bump_acl_epoch(kv)}
    for _ in range(5):
        kv.data.clear()
        bumped = bump_acl_epoch(kv)
        assert bumped not in earlier and bumped != "0"
        earlier.add(bumped)


@pytest.mark.asyncio
async def test_unsharing_and_visibility_cleanup_each_bump_the_epoch_but_sharing_does_not():
    redis = MagicMock()
    manager = KnowledgeOwnership(redis_client=redis)

    await manager.share_fact("f1", user_ids=["u2"], fact_metadata={"owner_id": "u1", "visibility": "private"})
    redis.set.assert_not_called()

    await manager.unshare_fact("f1", user_ids=["u2"], fact_metadata={"visibility": "shared", "shared_with": ["u2"]})
    assert redis.set.call_count == 1

    await manager.cleanup_ownership_indexes("f1", {"owner_id": "u1", "visibility": "shared", "shared_with": ["u2"]})
    assert redis.set.call_count == 2
