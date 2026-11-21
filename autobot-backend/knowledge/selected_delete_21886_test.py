# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The REAL ``delete_selected_facts`` against a faithful Redis fake (#21886, #17038).

The action tests stand a fake knowledge base in for it; this file runs the mixin itself, composed with the real
``CollectionsMixin`` and ``FactProjectionMixin``. ``delete_fact`` is a faithful stand-in for the one write it
delegates to (it reads through ``_read_fact_for_write``, removes the projection and the durable row, and reports
``status``); it carries the production ``invalidates_retrieval_caches`` wrapper, so the retrieval-cache bump on this
path is the real wrapper's.
"""

from unittest.mock import AsyncMock

import pytest

from knowledge import retrieval_invalidation
from knowledge.collections import CollectionsMixin
from knowledge.fact_projection import FactProjectionMixin
from knowledge.retrieval_invalidation import WRITE_ENTRY_POINTS, invalidates_retrieval_caches
from knowledge.selected_delete import SelectedFactsDeleteMixin


class FakeRedis:
    """Hashes and sets; the async surface the mixins call, and the sync ``hgetall`` the projection read uses."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict] = {}
        self.sets: dict[str, set] = {}

    async def smembers(self, key):
        return set(self.sets.get(key, ()))

    async def srem(self, key, *members):
        self.sets.get(key, set()).difference_update(members)

    async def scard(self, key):
        return len(self.sets.get(key, ()))

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def delete(self, *keys):
        for key in keys:
            self.hashes.pop(key, None)
            self.sets.pop(key, None)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))


class KnowledgeBase(SelectedFactsDeleteMixin, CollectionsMixin, FactProjectionMixin):
    """The production class's name, with the mixins under test and a faithful ``delete_fact``."""

    def __init__(self, redis: FakeRedis, rows: dict) -> None:
        self._redis, self.redis_client, self.rows = redis, redis, rows
        self.failing: set[str] = set()
        self.deleted: list[str] = []
        self.bm25_refreshes = 0

    def redis(self):
        return self._redis

    def _decode_fact_data(self, fact_data):
        return {(k.decode() if isinstance(k, bytes) else k): v for k, v in fact_data.items()}

    def _schedule_bm25_refresh(self) -> None:
        self.bm25_refreshes += 1

    async def delete_fact(self, fact_id: str, *, _skip_bm25_refresh: bool = False) -> dict:
        if fact_id in self.failing or await self._read_fact_for_write(fact_id) is None:
            return {"status": "error", "message": "Knowledge operation failed"}
        self._redis.hashes.pop(f"fact:{fact_id}", None)
        self.rows.pop(fact_id, None)
        self.deleted.append(fact_id)
        return {"status": "success", "fact_id": fact_id}


DELETE_FACT_REASON = next(e.reason for e in WRITE_ENTRY_POINTS if e.qualname == "KnowledgeBase.delete_fact")
# The production wrapper, applied to the one write this mixin delegates to (``invalidating_writes`` would also look
# for every other entry point on this partial class).
KnowledgeBase.delete_fact = invalidates_retrieval_caches(DELETE_FACT_REASON)(KnowledgeBase.delete_fact)


@pytest.fixture
def kb(monkeypatch):
    """f1: no collection. f2: in c1 and c2. f3: in c1 only. f4: durable row only, its Redis projection is gone."""
    redis = FakeRedis()
    rows = {f: {"content": f, "metadata": {}} for f in ("f1", "f2", "f3", "f4")}
    for fid in ("f1", "f2", "f3"):
        redis.hashes[f"fact:{fid}"] = {"content": fid, "metadata": "{}"}
    redis.sets.update(
        {
            "collection:facts:c1": {"f2", "f3"},
            "collection:facts:c2": {"f2"},
            "fact:collections:f2": {"c1", "c2"},
            "fact:collections:f3": {"c1"},
        }
    )
    redis.hashes.update({"collection:c1": {"fact_count": 2}, "collection:c2": {"fact_count": 1}})

    async def load_fact(fact_id):
        return rows.get(fact_id)

    monkeypatch.setattr("knowledge.fact_store.load_fact", load_fact)
    bump = AsyncMock()
    monkeypatch.setattr(retrieval_invalidation, "invalidate_retrieval_caches", bump)
    base = KnowledgeBase(redis, rows)
    base.bump = bump
    return base


@pytest.mark.asyncio
async def test_a_fact_in_no_collection_is_deleted_and_nothing_else(kb):
    result = await kb.delete_selected_facts(["f1"], confirm=True)
    assert result["success"] and result["deleted_count"] == 1
    assert (
        kb.deleted == ["f1"] and "fact:f1" not in kb.redis().hashes and "f3" in kb.redis().sets["collection:facts:c1"]
    )


@pytest.mark.asyncio
async def test_a_fact_in_two_collections_leaves_both_with_the_right_membership_and_count(kb):
    result = await kb.delete_selected_facts(["f2"], confirm=True)
    redis = kb.redis()
    assert result["success"] and kb.deleted == ["f2"]
    assert redis.sets["collection:facts:c1"] == {"f3"} and redis.sets["collection:facts:c2"] == set()
    assert redis.hashes["collection:c1"]["fact_count"] == 1 and redis.hashes["collection:c2"]["fact_count"] == 0
    assert "fact:collections:f2" not in redis.sets


@pytest.mark.asyncio
async def test_a_fact_whose_projection_is_missing_but_whose_row_exists_still_counts_and_is_deleted(kb):
    preview = await kb.delete_selected_facts(["f4", "nope"], confirm=False)
    assert preview["facts_to_delete"] == 1
    result = await kb.delete_selected_facts(["f4", "nope"], confirm=True)
    assert result["success"] and kb.deleted == ["f4"] and "f4" not in kb.rows


@pytest.mark.asyncio
async def test_a_count_above_the_approved_one_deletes_nothing(kb):
    result = await kb.delete_selected_facts(["f1", "f2"], confirm=True, approved={"facts": 1, "created_at": None})
    assert result["success"] is False and "exceed the approved count" in result["message"]
    assert kb.deleted == [] and kb.bump.await_count == 0


@pytest.mark.asyncio
async def test_a_partial_delete_failure_is_reported_and_leaves_the_failed_fact_linked(kb):
    kb.failing.add("f2")
    result = await kb.delete_selected_facts(["f1", "f2"], confirm=True)
    assert result["success"] is False and result["deleted_count"] == 1
    assert "only 1 of 2" in result["message"]
    assert kb.deleted == ["f1"] and kb.redis().sets["fact:collections:f2"] == {"c1", "c2"}


@pytest.mark.asyncio
async def test_each_deleted_fact_bumps_the_retrieval_epoch_through_the_wrapped_delete_fact(kb):
    await kb.delete_selected_facts(["f1", "f2"], confirm=True)
    assert [call.args for call in kb.bump.await_args_list] == [(DELETE_FACT_REASON,)] * 2
    assert kb.bm25_refreshes == 1
