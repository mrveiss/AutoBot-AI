# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Category counts and paging never include research-quarantined facts (#21957, part of #16665).

The real ``CategoriesMixin`` runs over the shared in-memory Redis; every fact is categorised through the
production assign path, so the quarantine index under test is the one production maintains.

Also covers #21984 (a deleted fact leaves its category set and quarantine index) and #21990 (the index is
synced from the stored metadata, and a rebuild batch never overwrites a concurrent update).
"""

import json

import pytest

from autobot_shared.ssot_config import config
from knowledge import category_quarantine
from knowledge.category_keys import FACTS_KEY, QUARANTINED_KEY, REBUILT_MARKER
from knowledge.category_quarantine import (
    INDEX_VERSION,
    add_to_category,
    rebuild_category_quarantine_index,
    sync_fact_quarantine,
)
from knowledge.facts import FactsMixin
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


async def _store_metadata(kb: CategoryKB, fact_id: str, metadata: dict) -> None:
    """What ``update_fact`` does: write the hash, then sync the index from the new metadata."""
    await kb.redis().hset(f"fact:{fact_id}", "metadata", json.dumps(metadata))
    await sync_fact_quarantine(kb.redis(), fact_id)


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

    await kb.redis().hset("fact:loose", "metadata", json.dumps(HELD))
    await sync_fact_quarantine(kb.redis(), "loose")

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


async def _write_metadata_only(kb: CategoryKB, fact_id: str, metadata: dict) -> None:
    """The hash write of ``update_fact``, before its index sync."""
    await kb.redis().hset(f"fact:{fact_id}", "metadata", json.dumps(metadata))


@pytest.mark.asyncio
async def test_two_out_of_order_updates_leave_the_index_matching_the_final_metadata():
    """#21990: A writes, B writes, B syncs, A syncs last -- A's in-memory view is stale, the stored one is B's."""
    kb = await _kb(servable=1, quarantined=0)
    client = kb.redis()
    await _write_metadata_only(kb, "s0", dict(HELD))  # update A
    await _write_metadata_only(kb, "s0", {"collection": "general"})  # update B: the final metadata

    await sync_fact_quarantine(client, "s0")  # B's sync
    await sync_fact_quarantine(client, "s0")  # A's sync, landing last

    assert await _total(kb) == 1
    assert "s0" not in kb.redis().sets.get(INDEX, set())


@pytest.mark.asyncio
async def test_an_update_landing_during_a_rebuild_batch_is_not_overwritten():
    """#21990: the rebuild reads s0 as servable; update_fact quarantines it and syncs; the rebuild then writes."""
    kb = await _kb(servable=1, quarantined=0)

    async def quarantine():
        await _store_metadata(kb, "s0", dict(HELD))

    kb.redis().after_metadata_read = quarantine
    await rebuild_category_quarantine_index(kb.redis())

    assert kb.redis().sets[INDEX] == {"s0"}
    assert await _total(kb) == 0


class _DeleteKB(FactsMixin, CategoryKB):
    """The real ``FactsMixin.delete_fact`` / ``delete_facts_by_session`` over the in-memory Redis."""

    vector_store = None

    def __init__(self):
        CategoryKB.__init__(self)
        self.session_facts: list = []
        self.cleanup_calls: list = []  # what ran after the durable delete

    def ensure_initialized(self):
        return None

    async def _read_fact_for_write(self, fact_id):
        exists = f"fact:{fact_id}" in self.redis().hashes
        return ({"content": f"fact {fact_id}"}, {}) if exists else None

    async def _durable_delete(self, fact_id):
        self.redis().hashes.pop(f"fact:{fact_id}", None)
        return True

    async def _cleanup_fact_mappings(self, fact_id, content, metadata):
        return None

    async def _decrement_stat(self, field, amount=1):
        self.cleanup_calls.append(field)

    async def _delete_fact_from_vector_store(self, fact_id):
        self.cleanup_calls.append("vector")

    def _schedule_bm25_refresh(self):
        self.cleanup_calls.append("bm25")

    async def get_facts_by_session(self, session_id):
        return list(self.session_facts)

    async def _batch_check_important_facts(self, fact_ids):
        return set()

    async def _cleanup_session_tracking(self, session_id, fact_ids):
        return None


async def _delete_kb() -> _DeleteKB:
    kb = _DeleteKB()
    for i in range(SERVABLE):
        await kb.add_fact(f"s{i}")
    await kb.add_fact("q0", **HELD)
    return kb


@pytest.mark.asyncio
async def test_deleting_a_categorised_fact_drops_it_from_the_set_and_keeps_counts_and_pages_exact():
    """#21984: N servable facts, one deleted -> total_count == N-1 and every page full."""
    kb = await _delete_kb()
    assert kb.redis().hashes["category:cat1"][b"fact_count"] == str(SERVABLE + 1).encode()  # via the assign flow

    assert (await kb.delete_fact("s0"))["status"] == "success"

    assert kb.redis().hashes["category:cat1"][b"fact_count"] == str(SERVABLE).encode()  # decremented once
    assert "s0" not in kb.redis().sets[MEMBERS]
    assert await _total(kb) == SERVABLE - 1
    pages = await _page_through(kb, limit=2)
    assert [p["returned_count"] for p in pages] == [2, 2]
    assert {p["total_count"] for p in pages} == {SERVABLE - 1}


@pytest.mark.asyncio
async def test_deleting_a_quarantined_fact_drops_it_from_the_quarantine_index():
    kb = await _delete_kb()

    await kb.delete_fact("q0")

    assert "q0" not in kb.redis().sets[MEMBERS]
    assert "q0" not in kb.redis().sets[INDEX]


@pytest.mark.asyncio
async def test_deleting_an_uncategorised_fact_touches_no_category_set():
    kb = _DeleteKB()
    await kb.add_fact("loose", category_id=None)

    assert (await kb.delete_fact("loose"))["status"] == "success"
    assert kb.redis().sets == {}


@pytest.mark.asyncio
async def test_delete_facts_by_session_drops_each_fact_from_set_and_index():
    kb = await _delete_kb()
    kb.session_facts = ["s0", "s1", "q0"]

    result = await kb.delete_facts_by_session("sess", preserve_important=False)

    assert result["deleted_count"] == 3
    assert kb.redis().sets[MEMBERS] == {"s2", "s3", "s4"}
    assert kb.redis().sets[INDEX] == set()
    assert await _total(kb) == SERVABLE - 2


@pytest.mark.asyncio
async def test_a_redis_failure_unindexing_a_deleted_fact_neither_fails_the_delete_nor_skips_its_cleanup(
    monkeypatch, caplog
):
    """#21984: the fact is gone; the stale derived id is logged, and the vector, stat and BM25 cleanup still run."""
    kb = await _delete_kb()

    async def boom(*args):
        raise ConnectionError("redis down")

    monkeypatch.setattr(category_quarantine, "remove_from_category", boom)
    with caplog.at_level("WARNING"):
        result = await kb.delete_fact("s0")

    assert result["status"] == "success"
    assert sorted(kb.cleanup_calls) == ["bm25", "total_facts", "total_vectors", "vector"]
    assert any("s0" in r.message and "cat1" in r.message and "ConnectionError" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_the_category_count_never_goes_below_zero():
    kb = _DeleteKB()
    await kb.add_fact("a")
    await kb.redis().hset("category:cat1", "fact_count", 0)

    await category_quarantine.decrement_category_count(kb.redis(), "cat1")

    assert kb.redis().hashes["category:cat1"][b"fact_count"] == b"0"


class _InterleavedRedis:
    """The in-memory Redis, running a writer between this sync's write and its re-read (first sadd), and
    before its first srem lands."""

    def __init__(self, inner):
        self.inner = inner
        self.after_first_sadd = None
        self.before_first_srem = None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def sadd(self, key, *values):
        await self.inner.sadd(key, *values)
        hook, self.after_first_sadd = self.after_first_sadd, None
        if hook:
            hook()

    async def srem(self, key, *values):
        hook, self.before_first_srem = self.before_first_srem, None
        if hook:
            hook()
        await self.inner.srem(key, *values)


@pytest.mark.asyncio
async def test_three_interleaved_writes_converge_on_the_final_stored_metadata():
    """#21990: S1 reads held, B stores servable, C stores held and syncs, S1's pending srem lands last."""
    kb = await _kb(servable=1, quarantined=0)
    hashes = kb.redis().hashes["fact:s0"]
    hashes[b"metadata"] = json.dumps(HELD).encode("utf-8")  # M1: held
    client = _InterleavedRedis(kb.redis())

    def writer_b():  # stores servable metadata, no sync yet
        hashes[b"metadata"] = json.dumps({"collection": "general"}).encode("utf-8")

    def writer_c():  # stores held metadata and syncs: its sadd lands before S1's srem
        hashes[b"metadata"] = json.dumps(HELD).encode("utf-8")
        kb.redis().sets.setdefault(INDEX, set()).add("s0")

    client.after_first_sadd = writer_b
    client.before_first_srem = writer_c
    await sync_fact_quarantine(client, "s0")

    assert kb.redis().sets[INDEX] == {"s0"}  # metadata says held, and the index agrees
    assert await _total(kb) == 0
