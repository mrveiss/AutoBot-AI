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


class _FakePipeline:
    """Minimal sync pipeline stand-in for ``redis_client.pipeline()``."""

    def __init__(self, facts: dict):
        self._facts = facts
        self._ops: list[str] = []

    def hgetall(self, key: str):
        self._ops.append(key)
        return self

    def execute(self):
        results = [self._facts.get(key, {}) for key in self._ops]
        self._ops = []
        return results


class _FakeRedisClient:
    """Minimal sync Redis stand-in exercising SMEMBERS + pipeline hgetall."""

    def __init__(self, category_sets: dict, facts: dict):
        self._category_sets = category_sets
        self._facts = facts
        self._cache: dict = {}

    def smembers(self, key: str):
        category = key.split(":", 2)[-1]
        return self._category_sets.get(category, set())

    def pipeline(self):
        return _FakePipeline(self._facts)

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

        monkeypatch.setattr(knowledge_module, "get_or_create_knowledge_base", _fake_get_or_create_knowledge_base)

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

        monkeypatch.setattr(knowledge_module, "get_or_create_knowledge_base", _fake_get_or_create_knowledge_base)

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

        monkeypatch.setattr(knowledge_module, "get_or_create_knowledge_base", _fake_get_or_create_knowledge_base)
        monkeypatch.setattr(knowledge_module, "_get_facts_by_category_legacy", _fail_if_called)

        req = SimpleNamespace(app=MagicMock())
        result = await knowledge_module.get_facts_by_category(
            admin_check=True, req=req, category="tools", limit=2, offset=10
        )

        assert result["categories"] == {}
        assert result["total_count"] == 3
        assert result["has_more"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
