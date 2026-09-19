# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""share_facts/get_shared_facts agree with check_access (#16709).

_share_single_fact used to hand-roll a second sharing index
(user:shared_facts:*) that set_owner/check_access never read, and never set
visibility=SHARED -- so a "shared" fact was refused to its own recipient.
These tests exercise the real KnowledgeOwnership.check_access, not a mock,
so they prove the round trip actually agrees in both directions.
"""

from __future__ import annotations

import json

import pytest

from knowledge.facts import FactsMixin
from knowledge.ownership import KnowledgeOwnership


class _FakeRedis:
    """Minimal synchronous stand-in for redis-py: hash + set ops, in-memory."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._sets: dict[str, set[str]] = {}

    def hget(self, key, field):
        return self._hashes.get(key, {}).get(field)

    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def hset(self, key, field, value):
        self._hashes.setdefault(key, {})[field] = value

    def sadd(self, key, *values):
        self._sets.setdefault(key, set()).update(values)

    def srem(self, key, *values):
        self._sets.get(key, set()).difference_update(values)

    def smembers(self, key):
        return set(self._sets.get(key, set()))


class _KB(FactsMixin):
    """Minimal FactsMixin host, real KnowledgeOwnership over the same fake redis."""

    def __init__(self, redis_client: _FakeRedis) -> None:
        self.redis_client = redis_client
        self.ownership_manager = KnowledgeOwnership(redis_client)


def _seed_private_fact(redis: _FakeRedis, fact_id: str, owner_id: str) -> None:
    redis.hset(
        f"fact:{fact_id}",
        "metadata",
        json.dumps({"owner_id": owner_id, "visibility": "private", "shared_with": []}),
    )
    redis.hset(f"fact:{fact_id}", "content", "secret content")


@pytest.mark.asyncio
async def test_share_facts_flips_visibility_to_shared():
    redis = _FakeRedis()
    _seed_private_fact(redis, "f1", owner_id="u1")
    kb = _KB(redis)

    result = await kb.share_facts(["f1"], shared_with=["u2"], shared_by="u1")

    assert result == {"shared_count": 1, "errors": []}
    metadata = json.loads(redis.hget("fact:f1", "metadata"))
    assert metadata["visibility"] == "shared"
    assert metadata["shared_with"] == ["u2"]


@pytest.mark.asyncio
async def test_recipient_passes_check_access_after_share_facts():
    """The bug this issue fixes: check_access must agree with share_facts."""
    redis = _FakeRedis()
    _seed_private_fact(redis, "f1", owner_id="u1")
    kb = _KB(redis)

    await kb.share_facts(["f1"], shared_with=["u2"], shared_by="u1")

    metadata = json.loads(redis.hget("fact:f1", "metadata"))
    assert await kb.ownership_manager.check_access("f1", "u2", metadata) is True
    assert await kb.ownership_manager.check_access("f1", "u99", metadata) is False


@pytest.mark.asyncio
async def test_get_shared_facts_lists_it_for_the_recipient():
    redis = _FakeRedis()
    _seed_private_fact(redis, "f1", owner_id="u1")
    kb = _KB(redis)

    await kb.share_facts(["f1"], shared_with=["u2"], shared_by="u1")
    shared = await kb.get_shared_facts("u2")

    assert [f["fact_id"] for f in shared] == ["f1"]


@pytest.mark.asyncio
async def test_get_shared_facts_agrees_with_check_access_for_a_stranger():
    """The other half of the bug: get_shared_facts must not list a fact
    check_access would refuse."""
    redis = _FakeRedis()
    _seed_private_fact(redis, "f1", owner_id="u1")
    kb = _KB(redis)

    await kb.share_facts(["f1"], shared_with=["u2"], shared_by="u1")

    assert await kb.get_shared_facts("u99") == []
