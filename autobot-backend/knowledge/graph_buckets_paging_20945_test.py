# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge-graph paging: permission filter FIRST, then count and page, for buckets and facts (#20945)."""

import pytest
from pydantic import ValidationError

from api.knowledge_graph_facts import visible_facts_page
from api.schemas_knowledge_graph import GraphRequest
from knowledge.graph_buckets import build_bucket_sections
from knowledge.graph_buckets_fakes_20945 import ALICE, ListingKB, client_with, fact, manager, viewer
from knowledge.graph_limits import GRAPH_MAX_OFFSET

_MINE = {"owner_id": ALICE}


def _page_ids(built, section="memory"):
    return [
        n["id"].rsplit(":", 1)[1]
        for n in built["nodes"]
        if n.get("section") == section and n["type"] == "bucket_record"
    ]


async def _memory(offset, limit, count=7):
    records = {"autobot_memory": [(f"m{i}", _MINE) for i in range(count)]}
    return await build_bucket_sections(await client_with(records), viewer(), manager(), limit=limit, offset=offset)


@pytest.mark.asyncio
async def test_bucket_records_page_in_a_stable_sorted_order():
    records = {"autobot_memory": [(f"m{i}", _MINE) for i in (3, 1, 2, 0)]}
    client = await client_with(records)
    first = await build_bucket_sections(client, viewer(), manager(), limit=2, offset=0)
    second = await build_bucket_sections(client, viewer(), manager(), limit=2, offset=2)
    assert _page_ids(first) == ["m0", "m1"] and _page_ids(second) == ["m2", "m3"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "offset,expected,limited",
    [(0, ["m0", "m1", "m2"], True), (3, ["m3", "m4", "m5"], True), (6, ["m6"], False), (7, [], False), (50, [], False)],
)
async def test_offset_edges_first_page_last_page_at_and_beyond_the_end(offset, expected, limited):
    built = await _memory(offset, 3)
    assert _page_ids(built) == expected
    report = built["sections"][0]
    assert (report["total"], report["returned"], report["limited"]) == (7, len(expected), limited)


@pytest.mark.asyncio
async def test_limit_zero_returns_no_records_but_still_reports_the_total():
    built = await _memory(0, 0)
    assert _page_ids(built) == [] and built["sections"][0]["total"] == 7 and built["sections"][0]["limited"] is True


@pytest.mark.asyncio
async def test_a_collection_longer_than_the_scan_cap_reports_a_lower_bound(monkeypatch):
    import knowledge.graph_buckets as buckets

    monkeypatch.setattr(buckets, "GRAPH_SCAN_LIMIT", 4)
    built = await _memory(0, 10, count=7)
    report = built["sections"][0]
    assert (report["total"], report["truncated"], report["limited"]) == (4, True, True)


def test_offset_has_an_env_backed_upper_bound():
    assert GraphRequest(offset=0).offset == 0 and GraphRequest(offset=GRAPH_MAX_OFFSET).offset == GRAPH_MAX_OFFSET
    with pytest.raises(ValidationError):
        GraphRequest(offset=GRAPH_MAX_OFFSET + 1)
    with pytest.raises(ValidationError):
        GraphRequest(offset=-1)


def _mixed(n=6):
    """Alternating alice's / bob's private facts: half are hidden from alice."""
    return [fact(f"f{i}", ALICE if i % 2 == 0 else "bob") for i in range(n)]


async def _facts(kb, offset=0, limit=2, category=None, who=ALICE, admin=False):
    return await visible_facts_page(kb, category, limit, offset, who, None, [], admin)


@pytest.mark.asyncio
async def test_facts_are_filtered_before_they_are_counted_and_paged():
    page = await _facts(ListingKB(_mixed()), limit=2)
    assert [f["id"] for f in page.facts] == ["f0", "f2"], "a full page of visible facts, not a short filtered one"
    assert page.total == 3, "the total counts only the facts alice may read, never the hidden three"


@pytest.mark.asyncio
async def test_facts_last_page_is_not_limited_and_beyond_the_end_is_empty():
    kb = ListingKB(_mixed())
    last = await _facts(kb, offset=2, limit=2)
    assert [f["id"] for f in last.facts] == ["f4"]
    assert (await _facts(kb, offset=3, limit=2)).facts == [] and (await _facts(kb, offset=99, limit=2)).facts == []


@pytest.mark.asyncio
async def test_the_category_filter_path_honours_offset():
    kb = ListingKB(_mixed())
    page = await _facts(kb, offset=1, limit=1, category="cat")
    assert [f["id"] for f in page.facts] == ["f2"] and page.total == 3
    assert all(call[0] == "category" for call in kb.calls) and kb.calls[0][2] == 0


@pytest.mark.asyncio
async def test_an_admin_sees_every_fact_and_a_ledger_holds_only_the_page():
    from knowledge.root_read import AdminReadLedger

    ledger = AdminReadLedger()
    page = await visible_facts_page(ListingKB(_mixed()), None, 2, 2, "root", None, [], ledger)
    assert page.total == 6 and [f["id"] for f in page.facts] == ["f2", "f3"]
    assert ledger.fact_ids == ["f2", "f3"]


@pytest.mark.asyncio
async def test_an_unreadable_listing_has_an_unknown_total_not_a_hidden_count():
    page = await _facts(ListingKB(_mixed()), who="carol")
    assert page.total == 0 and page.facts == []


@pytest.mark.asyncio
async def test_the_scan_cap_marks_a_truncated_total(monkeypatch):
    import api.knowledge_graph_facts as facts_mod

    monkeypatch.setattr(facts_mod, "GRAPH_SCAN_LIMIT", 4)
    monkeypatch.setattr(facts_mod, "SCAN_BATCH", 2)
    page = await _facts(ListingKB([fact(f"f{i}", ALICE) for i in range(9)]), limit=3)
    assert page.truncated is True and page.total == 4
