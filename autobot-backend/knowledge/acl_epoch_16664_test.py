# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The KB access-control epoch that partitions RAG caches over a revocation (#16664)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.acl_epoch import ACL_EPOCH_DATABASE, ACL_EPOCH_KEY, bump_acl_epoch, read_acl_epoch
from knowledge.ownership import KnowledgeOwnership


def test_the_bump_increments_the_one_counter_through_the_given_client():
    client = MagicMock()
    client.incr.return_value = 4

    assert bump_acl_epoch(client) == 4
    client.incr.assert_called_once_with(ACL_EPOCH_KEY)


def test_a_failed_bump_is_not_swallowed():
    """A revocation that did not invalidate the caches is a disclosure, so it must surface."""
    client = MagicMock()
    client.incr.side_effect = ConnectionError("redis down")

    with pytest.raises(ConnectionError):
        bump_acl_epoch(client)


@pytest.mark.asyncio
@pytest.mark.parametrize("stored, expected", [(None, "0"), (b"12", "12"), ("3", "3")])
async def test_the_epoch_reads_zero_before_the_first_bump_and_decodes_bytes(stored, expected):
    client = MagicMock(get=AsyncMock(return_value=stored))

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


@pytest.mark.asyncio
async def test_unsharing_and_visibility_cleanup_each_bump_the_epoch_but_sharing_does_not():
    redis = MagicMock()
    redis.incr.return_value = 1
    manager = KnowledgeOwnership(redis_client=redis)

    await manager.share_fact("f1", user_ids=["u2"], fact_metadata={"owner_id": "u1", "visibility": "private"})
    redis.incr.assert_not_called()

    await manager.unshare_fact("f1", user_ids=["u2"], fact_metadata={"visibility": "shared", "shared_with": ["u2"]})
    assert redis.incr.call_count == 1

    await manager.cleanup_ownership_indexes("f1", {"owner_id": "u1", "visibility": "shared", "shared_with": ["u2"]})
    assert redis.incr.call_count == 2
