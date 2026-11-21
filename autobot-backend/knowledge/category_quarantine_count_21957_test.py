# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Category counts and paging never include research-quarantined facts (#21957, part of #16665).

The real ``CategoriesMixin`` runs over the shared in-memory Redis; every fact is categorised through the
production assign path, so the quarantine index under test is the one production maintains.
"""

import json

import pytest

from autobot_shared.ssot_config import config
from knowledge.category_quarantine import QUARANTINED_KEY, rebuild_category_quarantine_index, sync_fact_quarantine
from knowledge.read_path_fakes_16665 import CategoryKB

HELD = {"collection": config.research_quarantine_collection}
SERVABLE = 5
QUARANTINED = 3


async def _kb(servable: int = SERVABLE, quarantined: int = QUARANTINED) -> CategoryKB:
    kb = CategoryKB()
    for i in range(servable):
        await kb.add_fact(f"s{i}")
    for i in range(quarantined):
        await kb.add_fact(f"q{i}", **HELD)
    return kb


async def _page_through(kb: CategoryKB, limit: int) -> list:
    pages, offset = [], 0
    while True:
        page = await kb.get_facts_in_category("cat1", limit=limit, offset=offset)
        pages.append(page)
        if not page["has_more"]:
            return pages
        offset += limit


@pytest.mark.asyncio
async def test_total_count_excludes_quarantined_facts_without_a_hash_read():
    kb = await _kb()
    kb.redis().reads.clear()

    result = await kb.get_facts_in_category("cat1", limit=0)

    assert result["total_count"] == SERVABLE
    assert kb.redis().reads == []


@pytest.mark.asyncio
async def test_paging_returns_exactly_the_servable_facts_and_full_pages():
    pages = await _page_through(await _kb(), limit=2)

    ids = [f["id"] for page in pages for f in page["facts"]]
    assert sorted(ids) == [f"s{i}" for i in range(SERVABLE)]
    assert [p["returned_count"] for p in pages] == [2, 2, 1]
    assert {p["total_count"] for p in pages} == {SERVABLE}


@pytest.mark.asyncio
async def test_has_more_is_false_once_only_quarantined_facts_remain():
    kb = await _kb(servable=2, quarantined=3)

    last = await kb.get_facts_in_category("cat1", limit=2, offset=0)

    assert (last["has_more"], last["total_count"]) == (False, 2)
    assert (await _kb(servable=0, quarantined=3)).redis().sets[QUARANTINED_KEY.format("cat1")]
    only_held = await (await _kb(servable=0, quarantined=3)).get_facts_in_category("cat1")
    assert (only_held["has_more"], only_held["total_count"], only_held["facts"]) == (False, 0, [])


@pytest.mark.asyncio
async def test_the_count_is_sensitive_to_the_index():
    """Without the quarantined ids indexed the count includes them: the pass above is the index's doing."""
    kb = await _kb()
    kb.redis().sets.pop(QUARANTINED_KEY.format("cat1"))

    result = await kb.get_facts_in_category("cat1", limit=0)

    assert result["total_count"] == SERVABLE + QUARANTINED


@pytest.mark.asyncio
async def test_a_quarantined_fact_the_index_missed_is_still_dropped_from_the_page():
    kb = await _kb(servable=1, quarantined=1)
    kb.redis().sets.pop(QUARANTINED_KEY.format("cat1"))

    result = await kb.get_facts_in_category("cat1")

    assert [f["id"] for f in result["facts"]] == ["s0"]


@pytest.mark.asyncio
async def test_leaving_a_category_leaves_the_quarantine_index():
    kb = await _kb(servable=0, quarantined=1)

    await kb._remove_from_old_category("q0", "cat2")

    assert kb.redis().sets["category:facts:cat1"] == set()
    assert kb.redis().sets[QUARANTINED_KEY.format("cat1")] == set()


class _SyncClient:
    """The sync client ``update_fact`` writes with, over the same in-memory store."""

    def __init__(self, store):
        self.store = store

    def hget(self, key, field):
        return self.store.hashes.get(key, {}).get(field.encode("utf-8"))

    def sadd(self, key, *values):
        self.store.sets.setdefault(key, set()).update(values)

    def srem(self, key, *values):
        self.store.sets.get(key, set()).difference_update(values)


@pytest.mark.asyncio
async def test_update_fact_moves_a_categorised_fact_in_and_out_of_the_index():
    kb = await _kb(servable=1, quarantined=0)
    client = _SyncClient(kb.redis())

    await sync_fact_quarantine(client, "s0", {"collection": HELD["collection"]})
    assert (await kb.get_facts_in_category("cat1", limit=0))["total_count"] == 0

    await sync_fact_quarantine(client, "s0", {"collection": "general"})
    assert (await kb.get_facts_in_category("cat1", limit=0))["total_count"] == 1


@pytest.mark.asyncio
async def test_update_fact_on_an_uncategorised_fact_touches_no_index():
    kb = CategoryKB()
    await kb.add_fact("loose", category_id=None)

    await sync_fact_quarantine(_SyncClient(kb.redis()), "loose", HELD)

    assert kb.redis().sets == {}


@pytest.mark.asyncio
async def test_the_rebuild_indexes_facts_categorised_before_the_index_and_runs_once():
    kb = await _kb(servable=2, quarantined=0)
    redis = kb.redis()
    meta = json.dumps({**HELD})
    await redis.hset("fact:old-q", mapping={"content": "old", "metadata": meta})
    await redis.sadd("category:facts:cat1", "old-q")

    assert (await kb.get_facts_in_category("cat1", limit=0))["total_count"] == 3
    assert await rebuild_category_quarantine_index(redis) == 3
    assert (await kb.get_facts_in_category("cat1", limit=0))["total_count"] == 2
    assert await rebuild_category_quarantine_index(redis) == 0
