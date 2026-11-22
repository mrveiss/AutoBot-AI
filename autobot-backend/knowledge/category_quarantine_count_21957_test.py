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
from knowledge.category_keys import FACTS_KEY, QUARANTINED_KEY, REBUILT_MARKER
from knowledge.category_quarantine import (
    INDEX_VERSION,
    add_to_category,
    rebuild_category_quarantine_index,
    sync_fact_quarantine,
)
from services.kb_wipe_redis import KB_KEY_PREFIXES
from testkit.read_path_fakes_16665 import CategoryKB

HELD = {"collection": config.research_quarantine_collection}
SERVABLE = 5
QUARANTINED = 3
INDEX = QUARANTINED_KEY.format("cat1")
MEMBERS = FACTS_KEY.format("cat1")


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


async def _total(kb: CategoryKB, **kwargs) -> int:
    return (await kb.get_facts_in_category("cat1", limit=0, **kwargs))["total_count"]


@pytest.mark.asyncio
async def test_total_count_excludes_quarantined_facts_without_a_hash_read():
    kb = await _kb()
    kb.redis().reads.clear()

    result = await kb.get_facts_in_category("cat1", limit=0)

    assert result["total_count"] == SERVABLE
    assert kb.redis().reads == []  # no hget, hgetall, hmget or hscan of any fact


@pytest.mark.asyncio
async def test_paging_returns_exactly_the_servable_facts_and_full_pages():
    pages = await _page_through(await _kb(), limit=2)

    ids = [f["id"] for page in pages for f in page["facts"]]
    assert sorted(ids) == [f"s{i}" for i in range(SERVABLE)]
    assert [p["returned_count"] for p in pages] == [2, 2, 1]
    assert {p["total_count"] for p in pages} == {SERVABLE}


@pytest.mark.asyncio
async def test_has_more_is_false_once_only_quarantined_facts_remain():
    last = await (await _kb(servable=2, quarantined=3)).get_facts_in_category("cat1", limit=2, offset=0)
    only_held = await (await _kb(servable=0, quarantined=3)).get_facts_in_category("cat1")

    assert (last["has_more"], last["total_count"]) == (False, 2)
    assert (only_held["has_more"], only_held["total_count"], only_held["facts"]) == (False, 0, [])


@pytest.mark.asyncio
async def test_descendant_categories_count_and_page_without_quarantined_facts():
    kb = CategoryKB()
    kb.redis().sets["category:children:cat1"] = {"cat2"}
    await kb.add_fact("a")
    await kb.add_fact("b", category_id="cat2")
    await kb.add_fact("held", category_id="cat2", **HELD)

    result = await kb.get_facts_in_category("cat1", include_descendants=True)

    assert (result["total_count"], sorted(f["id"] for f in result["facts"])) == (2, ["a", "b"])
    assert await _total(kb) == 1  # without descendants only cat1 itself


@pytest.mark.asyncio
async def test_the_count_is_sensitive_to_the_index():
    """Without the quarantined ids indexed the count includes them: the pass above is the index's doing."""
    kb = await _kb()
    kb.redis().sets.pop(INDEX)

    assert await _total(kb) == SERVABLE + QUARANTINED


@pytest.mark.asyncio
async def test_a_quarantined_fact_the_index_missed_is_still_dropped_from_the_page():
    kb = await _kb(servable=1, quarantined=1)
    kb.redis().sets.pop(INDEX)

    result = await kb.get_facts_in_category("cat1")

    assert [f["id"] for f in result["facts"]] == ["s0"]


@pytest.mark.asyncio
async def test_leaving_a_category_leaves_the_quarantine_index_in_one_transaction():
    kb = await _kb(servable=0, quarantined=1)
    before = len(kb.redis().executed_batches())

    await kb._remove_from_old_category("q0", "cat2")

    assert kb.redis().sets[MEMBERS] == kb.redis().sets[INDEX] == set()
    assert kb.redis().executed_batches()[before:] == [[("srem", MEMBERS, "q0"), ("srem", INDEX, "q0")]]


@pytest.mark.asyncio
async def test_deleting_a_category_removes_its_quarantine_index():
    kb = await _kb()
    kb.redis().hashes["category:cat1"] = {b"path": b"research"}

    await kb._delete_category_records("cat1")

    assert MEMBERS not in kb.redis().sets
    assert INDEX not in kb.redis().sets


@pytest.mark.asyncio
async def test_joining_a_category_and_its_index_entry_are_one_transaction():
    kb = CategoryKB()
    await kb.add_fact("q", category_id=None, **HELD)
    before = len(kb.redis().executed_batches())

    await add_to_category(kb.redis(), "q", "cat1")

    assert kb.redis().executed_batches()[before:] == [[("sadd", MEMBERS, "q"), ("sadd", INDEX, "q")]]


@pytest.mark.asyncio
async def test_a_crash_before_the_transaction_leaves_neither_set_changed():
    kb = CategoryKB()
    await kb.add_fact("q", category_id=None, **HELD)
    kb.redis().next_pipeline_errors = [ConnectionError("connection lost before EXEC")]

    with pytest.raises(ConnectionError):
        await add_to_category(kb.redis(), "q", "cat1")

    assert MEMBERS not in kb.redis().sets
    assert INDEX not in kb.redis().sets


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


async def _store_metadata(kb: CategoryKB, fact_id: str, metadata: dict) -> None:
    """What ``update_fact`` does: write the hash, then sync the index from the new metadata."""
    await kb.redis().hset(f"fact:{fact_id}", "metadata", json.dumps(metadata))
    await sync_fact_quarantine(_SyncClient(kb.redis()), fact_id, metadata)


@pytest.mark.asyncio
async def test_update_fact_moves_a_categorised_fact_in_and_out_of_the_index():
    kb = await _kb(servable=1, quarantined=0)

    await _store_metadata(kb, "s0", dict(HELD))
    assert await _total(kb) == 0

    await _store_metadata(kb, "s0", {"collection": "general"})
    assert await _total(kb) == 1


@pytest.mark.asyncio
async def test_update_fact_on_an_uncategorised_fact_touches_no_index():
    kb = CategoryKB()
    await kb.add_fact("loose", category_id=None)

    await sync_fact_quarantine(_SyncClient(kb.redis()), "loose", HELD)

    assert kb.redis().sets == {}


@pytest.mark.asyncio
async def test_a_promotion_between_the_assign_read_and_write_leaves_the_fact_servable():
    """The race: assign reads the quarantined metadata, update_fact promotes (a no-op srem), assign adds."""
    kb = CategoryKB()
    await kb.add_fact("p", category_id=None, **HELD)

    async def promote():
        await _store_metadata(kb, "p", {"collection": "general"})

    kb.redis().after_metadata_read = promote
    await kb._assign_fact_to_category("p", "cat1")

    assert await _total(kb) == 1
    assert INDEX not in kb.redis().sets or "p" not in kb.redis().sets[INDEX]


@pytest.mark.asyncio
async def test_a_quarantine_between_the_assign_read_and_write_leaves_the_fact_hidden():
    kb = CategoryKB()
    await kb.add_fact("r", category_id=None)

    async def quarantine():
        await _store_metadata(kb, "r", dict(HELD))

    kb.redis().after_metadata_read = quarantine
    await kb._assign_fact_to_category("r", "cat1")

    assert await _total(kb) == 0


@pytest.mark.asyncio
async def test_the_rebuild_indexes_facts_categorised_before_the_index_and_runs_once():
    kb = await _kb(servable=2, quarantined=0)
    redis = kb.redis()
    await redis.hset("fact:old-q", mapping={"content": "old", "metadata": json.dumps(HELD)})
    await redis.sadd(MEMBERS, "old-q")

    assert await _total(kb) == 3
    assert await rebuild_category_quarantine_index(redis) == 3  # facts visited
    assert await _total(kb) == 2
    assert redis.strings[REBUILT_MARKER] == INDEX_VERSION.encode("utf-8")  # bytes, as Redis returns it
    assert await rebuild_category_quarantine_index(redis) == 0


@pytest.mark.asyncio
async def test_the_rebuild_heals_a_wrong_index_in_both_directions():
    kb = await _kb(servable=1, quarantined=1)
    kb.redis().sets[INDEX] = {"s0"}  # servable hidden by mistake, quarantined left unindexed

    assert await rebuild_category_quarantine_index(kb.redis()) == 2

    assert kb.redis().sets[INDEX] == {"q0"}
    assert await _total(kb) == 1


@pytest.mark.asyncio
async def test_a_stale_marker_reruns_the_rebuild_and_a_current_one_skips_it():
    kb = await _kb(servable=1, quarantined=1)
    kb.redis().sets[INDEX] = set()
    kb.redis().strings[REBUILT_MARKER] = INDEX_VERSION.encode("utf-8")
    assert await rebuild_category_quarantine_index(kb.redis()) == 0
    assert kb.redis().sets[INDEX] == set()

    kb.redis().strings[REBUILT_MARKER] = b"0"
    assert await rebuild_category_quarantine_index(kb.redis()) == 2
    assert kb.redis().sets[INDEX] == {"q0"}


def test_a_kb_wipe_drops_the_index_and_its_marker():
    assert {QUARANTINED_KEY.format(""), REBUILT_MARKER, FACTS_KEY.format("")} <= set(KB_KEY_PREFIXES)
