#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Issue #12370: the ``GET /api/knowledge_base/facts/by_category`` browse list
must ship only a snippet (``content``), never the entire document
(``full_content``). The full text is lazy-loaded per fact via
``GET /api/knowledge_base/fact/{fact_key}``.

These tests pin the payload contract:
    * the list-item builder omits ``full_content`` and truncates ``content``;
    * the list response model no longer declares ``full_content``;
    * the detail endpoint's content extractor still returns the full text.

Issue #12394: the same endpoint was unbounded (every fact in every category,
every call). These tests pin the pagination contract:
    * ``limit``/``offset`` window each category's fact index deterministically
      (SMEMBERS + sorted slice, not SRANDMEMBER — see ``_fetch_category_fact_ids``);
    * ``total_count``/``has_more`` reflect the true per-category size, not just
      what was returned on this page;
    * an out-of-range ``offset`` on an existing category index returns an
      empty page WITHOUT falling back to the expensive full-keyspace SCAN
      (that fallback is reserved for "no index at all").
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testkit.fake_redis_pipeline import FakePipeline


@pytest.fixture
def large_fact_data():
    """Redis ``hgetall`` shape (bytes keys/values) for a >500-char document."""
    content = "x" * 1200
    return content, {
        b"content": content.encode("utf-8"),
        b"metadata": json.dumps({"title": "Big Doc", "type": "note"}).encode("utf-8"),
    }


class TestBrowseListOmitsFullContent:
    """The browse list ships a snippet only — never full_content."""

    def test_process_fact_data_omits_full_content(self, large_fact_data):
        from api.knowledge import _process_fact_data

        content, fact_data = large_fact_data
        result = _process_fact_data(fact_data, "tools", "fact:abc")

        assert result is not None
        # Issue #12370: the entire document must NOT be in the list item.
        assert "full_content" not in result
        # Snippet is truncated to 500 chars + ellipsis.
        assert result["content"].endswith("...")
        assert len(result["content"]) == 503
        assert result["content"][:-3] == content[:500]
        # The fields a browse list actually needs are present.
        assert result["key"] == "fact:abc"
        assert result["title"] == "Big Doc"
        assert result["category"] == "tools"
        assert result["type"] == "note"
        assert isinstance(result["metadata"], dict)

    def test_short_fact_content_not_ellipsised(self):
        from api.knowledge import _process_fact_data

        short = "nmap is a network scanner"
        fact_data = {
            b"content": short.encode("utf-8"),
            b"metadata": json.dumps({"title": "nmap"}).encode("utf-8"),
        }
        result = _process_fact_data(fact_data, "tools", "fact:xyz")

        assert result is not None
        assert "full_content" not in result
        # Short facts arrive whole (no trailing ellipsis) so the client
        # renders them without a detail round-trip.
        assert result["content"] == short

    def test_response_model_no_longer_declares_full_content(self):
        from knowledge.schemas.entries import FactByCategoryEntry

        # Issue #12370: contract (OpenAPI/api.ts) must not advertise the field.
        assert "full_content" not in FactByCategoryEntry.model_fields
        assert "content" in FactByCategoryEntry.model_fields


class TestDetailEndpointCarriesFullContent:
    """The per-fact detail endpoint remains the lazy-load source of truth."""

    def test_extract_fact_content_returns_full_untruncated_text(self, large_fact_data):
        from api.knowledge import _extract_fact_content

        content, _ = large_fact_data
        # Detail endpoint returns the whole document, untruncated, in `content`.
        extracted = _extract_fact_content({"content": content})

        assert extracted == content
        assert len(extracted) == 1200
        assert not extracted.endswith("...")

    def test_detail_response_model_exposes_content(self):
        from knowledge.schemas.entries import FactByKeyResponse

        # The detail response carries the full document under `content`.
        assert "content" in FactByKeyResponse.model_fields


class _FakeRedisClient:
    """Minimal sync Redis stand-in exercising SMEMBERS + pipeline hgetall."""

    def __init__(self, category_sets: dict, facts: dict):
        self._category_sets = category_sets
        self._facts = facts
        self._cache: dict = {}

    def smembers(self, key: str):
        category = key.split(":", 2)[-1]
        return self._category_sets.get(category, set())

    def hgetall(self, key: str):
        return self._facts.get(key, {})

    def pipeline(self):
        return FakePipeline(self)

    def get(self, key: str):
        return self._cache.get(key)

    def setex(self, key: str, _ttl: int, value):
        self._cache[key] = value


def _make_fake_kb(category_sets: dict, fact_ids: list[str]):
    facts = {
        f"fact:{fid}": {
            b"content": f"content for {fid}".encode("utf-8"),
            b"metadata": json.dumps({"title": f"Title {fid}"}).encode("utf-8"),
        }
        for fid in fact_ids
    }
    kb = MagicMock()
    kb.redis_client = _FakeRedisClient(category_sets, facts)
    return kb


class TestFetchCategoryFactIdsPagination:
    """Issue #12394: ``_fetch_category_fact_ids`` windows deterministically."""

    @pytest.mark.asyncio
    async def test_page_is_deterministic_sorted_slice(self):
        from api.knowledge import _fetch_category_fact_ids

        kb = _make_fake_kb(
            {"tools": {b"3", b"1", b"5", b"2", b"4"}},
            fact_ids=["1", "2", "3", "4", "5"],
        )

        category_fact_ids, category_totals = await _fetch_category_fact_ids(kb, ["tools"], limit=2, offset=1)

        assert category_fact_ids == {"tools": ["2", "3"]}
        assert category_totals == {"tools": 5}

    @pytest.mark.asyncio
    async def test_repeated_calls_return_identical_page(self):
        """SRANDMEMBER would re-sample randomly; SMEMBERS+sort must not."""
        from api.knowledge import _fetch_category_fact_ids

        kb = _make_fake_kb(
            {"tools": {b"3", b"1", b"5", b"2", b"4"}},
            fact_ids=["1", "2", "3", "4", "5"],
        )

        first, _ = await _fetch_category_fact_ids(kb, ["tools"], limit=2, offset=1)
        second, _ = await _fetch_category_fact_ids(kb, ["tools"], limit=2, offset=1)

        assert first == second == {"tools": ["2", "3"]}

    @pytest.mark.asyncio
    async def test_offset_beyond_total_returns_empty_page_with_correct_total(self):
        from api.knowledge import _fetch_category_fact_ids

        kb = _make_fake_kb(
            {"tools": {b"1", b"2", b"3"}},
            fact_ids=["1", "2", "3"],
        )

        category_fact_ids, category_totals = await _fetch_category_fact_ids(kb, ["tools"], limit=2, offset=10)

        assert category_fact_ids == {}
        assert category_totals == {"tools": 3}


class TestGetFactsByCategoryRoutePagination:
    """Issue #12394: end-to-end pagination contract of the route handler."""

    @pytest.mark.asyncio
    async def test_response_carries_limit_offset_total_count_has_more(self, monkeypatch):
        from api import knowledge as knowledge_module

        kb = _make_fake_kb(
            {"tools": {b"1", b"2", b"3", b"4", b"5"}},
            fact_ids=["1", "2", "3", "4", "5"],
        )

        async def _fake_get_or_create_knowledge_base(_app, **_kwargs):
            return kb

        monkeypatch.setattr(
            knowledge_module,
            "get_or_create_knowledge_base",
            _fake_get_or_create_knowledge_base,
        )

        req = SimpleNamespace(app=MagicMock())
        result = await knowledge_module.get_facts_by_category(
            admin_check=True, req=req, category="tools", limit=2, offset=1
        )

        assert result["limit"] == 2
        assert result["offset"] == 1
        assert result["total_count"] == 5
        assert result["total_facts"] == 2
        assert result["has_more"] is True
        assert [f["key"] for f in result["categories"]["tools"]] == ["fact:2", "fact:3"]

    @pytest.mark.asyncio
    async def test_last_page_reports_has_more_false(self, monkeypatch):
        from api import knowledge as knowledge_module

        kb = _make_fake_kb(
            {"tools": {b"1", b"2", b"3", b"4", b"5"}},
            fact_ids=["1", "2", "3", "4", "5"],
        )

        async def _fake_get_or_create_knowledge_base(_app, **_kwargs):
            return kb

        monkeypatch.setattr(
            knowledge_module,
            "get_or_create_knowledge_base",
            _fake_get_or_create_knowledge_base,
        )

        req = SimpleNamespace(app=MagicMock())
        result = await knowledge_module.get_facts_by_category(
            admin_check=True, req=req, category="tools", limit=2, offset=4
        )

        assert result["total_count"] == 5
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_out_of_range_offset_does_not_trigger_legacy_scan_fallback(self, monkeypatch):
        """Issue #12394 fix: an empty PAGE on an existing index must not be
        mistaken for a MISSING index (which would trigger the expensive
        full-keyspace SCAN fallback)."""
        from api import knowledge as knowledge_module

        kb = _make_fake_kb(
            {"tools": {b"1", b"2", b"3"}},
            fact_ids=["1", "2", "3"],
        )

        async def _fake_get_or_create_knowledge_base(_app, **_kwargs):
            return kb

        async def _fail_if_called(*_args, **_kwargs):
            raise AssertionError("legacy SCAN fallback must not run when a category index exists")

        monkeypatch.setattr(
            knowledge_module,
            "get_or_create_knowledge_base",
            _fake_get_or_create_knowledge_base,
        )
        monkeypatch.setattr(knowledge_module, "_get_facts_by_category_legacy", _fail_if_called)

        req = SimpleNamespace(app=MagicMock())
        result = await knowledge_module.get_facts_by_category(
            admin_check=True, req=req, category="tools", limit=2, offset=10
        )

        assert result["categories"] == {}
        assert result["total_count"] == 3
        assert result["has_more"] is False


class _FactRedis:
    """Async Redis holding ``fact:<id>`` hashes (bytes, as the KB writes them) plus same-prefix non-fact keys.

    ``scan`` walks the key list ``page`` keys at a time and returns an integer cursor, as SCAN does.
    """

    def __init__(self, hashes: dict, extra_keys=(), page: int = 3):
        self.hashes = hashes
        self.keys = list(hashes) + list(extra_keys)
        self.page = page
        self.read = []  # every read command issued, so a test can assert what was (not) fetched

    async def scan(self, cursor=0, match=None, count=None):
        chunk = self.keys[cursor : cursor + self.page]
        nxt = cursor + self.page
        return (0 if nxt >= len(self.keys) else nxt), chunk

    async def scan_iter(self, match=None, count=None):
        for key in self.keys:
            yield key

    def pipeline(self, transaction=True):
        from testkit.fake_redis_pipeline import FakeAsyncPipeline

        return FakeAsyncPipeline(self, transaction=transaction)

    async def hgetall(self, key):
        self.read.append(("hgetall", key))
        if key not in self.hashes:
            raise TypeError("WRONGTYPE: not a hash")
        return self.hashes[key]

    async def hget(self, key, field):
        self.read.append(("hget", key, field))
        if key not in self.hashes:
            raise TypeError("WRONGTYPE: not a hash")
        return self.hashes[key].get(field)

    async def hstrlen(self, key, field):
        self.read.append(("hstrlen", key, field))
        if key not in self.hashes:
            raise TypeError("WRONGTYPE: not a hash")
        return len(self.hashes[key].get(field, ""))


def _fact_kb(n: int, extra_keys=(), page: int = 3):
    """A KB whose readers are the real ``FactsMixin`` ones over fact hashes shaped as ``store_fact`` writes them."""
    from knowledge.facts import FactsMixin

    hashes = {
        f"fact:id-{i}": {
            "content": f"c{i}",
            "metadata": json.dumps({"title": f"t{i}", "category": "even" if i % 2 == 0 else "odd", "type": "note"}),
            "timestamp": f"2026-01-{i + 1:02d}",
        }
        for i in range(n)
    }
    redis = _FactRedis(hashes, extra_keys, page)
    kb = SimpleNamespace(
        redis=lambda: redis,
        ensure_initialized=lambda: None,
        redis_client=SimpleNamespace(hscan=None, hgetall=None),  # the removed knowledge_base:facts hash: not read
    )
    kb._process_fact_data = lambda key, data, coll=None: FactsMixin._process_fact_data(kb, key, data, coll)
    kb.get_all_facts = lambda **kw: FactsMixin.get_all_facts(kb, **kw)
    return kb


class TestEntriesEndpointServesWhatItDeclares:
    """Issue #17530: ``GET /entries`` lists the ``fact:<id>`` store by bare id and pages without loss."""

    @staticmethod
    def _client(kb):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import api.knowledge as kn
        from auth_middleware import check_admin_permission

        app = FastAPI()
        app.include_router(kn.router, prefix="/api/knowledge_base")
        app.dependency_overrides[check_admin_permission] = lambda: True
        return TestClient(app), kn

    def test_fact_hashes_are_listed_by_bare_id_not_the_dead_hash(self):
        from unittest.mock import AsyncMock, patch

        kb = _fact_kb(2, page=10)
        client, kn = self._client(kb)
        with patch.object(kn, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
            resp = client.get("/api/knowledge_base/entries")
        assert resp.status_code == 200
        body = resp.json()
        assert {e["id"] for e in body["entries"]} == {"id-0", "id-1"}  # the id kb.update_fact/delete_fact key on
        assert {e["content"] for e in body["entries"]} == {"c0", "c1"}
        assert all("source" in e and "key" not in e for e in body["entries"])

    def test_cursor_walk_over_more_than_limit_loses_nothing_and_skips_non_facts(self):
        from unittest.mock import AsyncMock, patch

        extra = ["fact:collections:id-0", "fact:versions:id-1", "fact:origin:session:id-2"]
        kb = _fact_kb(7, extra_keys=extra, page=3)
        client, kn = self._client(kb)
        seen, cursor = [], "0"
        with patch.object(kn, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
            for _ in range(10):
                body = client.get(f"/api/knowledge_base/entries?limit=2&cursor={cursor}").json()
                seen += [e["id"] for e in body["entries"]]
                cursor = body["next_cursor"]
                if not body["has_more"]:
                    break
        assert sorted(seen) == sorted(f"id-{i}" for i in range(7))
        assert len(seen) == len(set(seen))

    def test_category_filter_applies_to_the_page(self):
        from unittest.mock import AsyncMock, patch

        kb = _fact_kb(4, page=10)
        client, kn = self._client(kb)
        with patch.object(kn, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
            body = client.get("/api/knowledge_base/entries?category=odd").json()
        assert {e["id"] for e in body["entries"]} == {"id-1", "id-3"}


class TestWholeStoreReadersUseFactHashes:
    """Issue #17530: categories / detailed stats read ``fact:<id>``, never ``knowledge_base:facts``."""

    @pytest.mark.asyncio
    async def test_detailed_stats_counts_the_fact_hashes(self):
        import api.knowledge as kn
        from knowledge.fact_aggregate import fact_rows

        kb = _fact_kb(5, extra_keys=["fact:collections:x"], page=2)
        cats, srcs, types, sizes = kn._analyze_facts_for_stats(await fact_rows(kb))
        assert cats == {"even": 3, "odd": 2}
        assert types == {"note": 5} and len(sizes) == 5

    @pytest.mark.asyncio
    async def test_get_all_facts_survives_same_prefix_non_hash_keys(self):
        """#17530: a ``fact:collections:<id>`` set (and the other ``fact:`` families) must not fail the read."""
        kb = _fact_kb(
            3,
            extra_keys=[
                "fact:collections:id-0",
                "fact:origin:session:id-1",
                "fact:versions:id-2",
                "fact:version:meta:id-2",
            ],
            page=2,
        )
        facts = await kb.get_all_facts()
        assert sorted(f["fact_id"] for f in facts) == ["id-0", "id-1", "id-2"]

    @pytest.mark.asyncio
    async def test_aggregate_reads_metadata_and_size_never_content_and_skips_non_hashes(self):
        """#17530: the whole-store counts fetch no fact text, and never touch a non-hash ``fact:`` key."""
        from knowledge.fact_aggregate import fact_rows

        extra = ["fact:collections:id-0", "fact:origin:session:id-1"]
        kb = _fact_kb(4, extra_keys=extra, page=2)
        rows = await fact_rows(kb)
        redis = kb.redis()
        assert sorted(r["metadata"]["title"] for r in rows) == ["t0", "t1", "t2", "t3"]
        assert [r["size"] for r in rows] == [2] * 4  # len("c<i>")
        assert not [c for c in redis.read if c[0] == "hgetall" or (len(c) > 2 and c[2] == "content" and c[0] == "hget")]
        assert not [c for c in redis.read if c[1] in extra]

    @pytest.mark.asyncio
    async def test_aggregate_is_cached_for_the_ttl(self, monkeypatch):
        import knowledge.fact_aggregate as agg

        kb = _fact_kb(2, page=10)
        monkeypatch.setattr(agg, "FACT_AGGREGATE_TTL_SECONDS", 30)
        await agg.fact_rows(kb)
        reads = len(kb.redis().read)
        await agg.fact_rows(kb)
        assert len(kb.redis().read) == reads  # second call served from the cache
        monkeypatch.setattr(agg, "FACT_AGGREGATE_TTL_SECONDS", 0)
        await agg.fact_rows(kb)
        assert len(kb.redis().read) > reads

    @pytest.mark.asyncio
    async def test_categories_degrade_to_zero_counts_when_redis_fails(self):
        """#17530: a Redis error in the count read does not become a 500 (as before the move off the dead hash)."""
        from unittest.mock import AsyncMock, patch

        import api.knowledge as kn

        kb = SimpleNamespace(
            get_stats=AsyncMock(return_value={"categories": ["a"]}),
            ensure_initialized=lambda: None,
            redis=lambda: (_ for _ in ()).throw(ConnectionError("down")),
        )
        req = SimpleNamespace(app=object())
        with patch.object(kn, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
            resp = await kn.get_knowledge_categories(admin_check=True, req=req)
        dump = [c if isinstance(c, dict) else c.model_dump() for c in resp.categories]
        assert [(c["name"], c["count"]) for c in dump] == [("a", 0)]
        assert resp.degraded is True  # a failed read is flagged, never a confident zero

    @pytest.mark.asyncio
    async def test_detailed_stats_flags_a_failed_fact_read_as_degraded(self, caplog):
        from unittest.mock import AsyncMock, patch

        import api.knowledge as kn

        kb = SimpleNamespace(
            get_stats=AsyncMock(return_value={"initialized": True}),
            ensure_initialized=lambda: None,
            redis=lambda: (_ for _ in ()).throw(ConnectionError("down")),
        )
        with patch.object(kn, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
            with caplog.at_level("WARNING"):
                resp = await kn.get_detailed_stats(admin_check=True, req=SimpleNamespace(app=object()))
        assert resp.degraded is True and resp.category_breakdown == {}
        assert any(r.levelname == "WARNING" and "Redis read failed" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_aggregate_and_listing_show_facts_stored_under_colon_ids(self):
        """#17530: ids such as ``claude_memory:<owner>:<slug>`` are real; the readers must list them whole."""
        import knowledge.fact_aggregate as agg
        from knowledge.fact_stream import get_facts_page

        kb = _fact_kb(1, extra_keys=["fact:collections:id-0"], page=10)
        meta = json.dumps({"title": "m", "category": "memory", "type": "note"})
        for fid in ("claude_memory:u1:slug", "gdrive:c1:file:/a.md"):
            kb.redis().hashes["fact:" + fid] = {"content": "xy", "metadata": meta, "timestamp": "2026-01-01"}
            kb.redis().keys.append("fact:" + fid)
        assert len(await agg.fact_rows(kb)) == 3
        _, page = await get_facts_page(kb, 0, 10)
        assert sorted(f["fact_id"] for f in page) == ["claude_memory:u1:slug", "gdrive:c1:file:/a.md", "id-0"]

    @pytest.mark.asyncio
    async def test_concurrent_cold_requests_share_one_scan_and_a_write_invalidates_the_cache(self, monkeypatch):
        import asyncio

        import knowledge.fact_aggregate as agg

        kb = _fact_kb(3, page=10)
        monkeypatch.setattr(agg, "FACT_AGGREGATE_TTL_SECONDS", 30)
        first = await asyncio.gather(*[agg.fact_rows(kb) for _ in range(5)])
        assert len({id(r) for r in first}) == 1 and isinstance(first[0], tuple)
        assert len([c for c in kb.redis().read if c[0] == "hget" and c[2] == "metadata"]) == 3  # ONE scan, not five
        reads = len(kb.redis().read)
        await agg.fact_rows(kb)
        assert len(kb.redis().read) == reads
        agg.invalidate_fact_rows(kb)
        await agg.fact_rows(kb)
        assert len(kb.redis().read) > reads

    @pytest.mark.asyncio
    async def test_man_page_parser_reads_the_fact_dict(self):
        import api.knowledge as kn

        assert kn._parse_man_page_fact({"metadata": {"type": "manual_page", "created_at": "t"}}) == (True, False, "t")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
