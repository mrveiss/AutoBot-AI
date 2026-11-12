# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Review findings of the knowledge-graph buckets: tenant, quarantine, stored names, sources, scan edges (#20945)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.knowledge_graph_facts import visible_facts_page
from knowledge.graph_bucket_visibility import collection_in_scope
from knowledge.graph_buckets import build_bucket_sections, section_for
from knowledge.graph_limits import SCAN_BATCH
from knowledge.root_read import AdminReadLedger
from tests.fixtures.graph_buckets_fakes_20945 import (
    ALICE,
    TENANT_A,
    TENANT_B,
    ListingKB,
    client_with,
    fact,
    manager,
    viewer,
)


def _tenant_fact(fact_id, owner, tenant):
    f = fact(fact_id, owner)
    f["metadata"]["organization_id"] = tenant
    return f


@pytest.mark.asyncio
async def test_a_tenant_admin_does_not_read_another_tenants_facts_but_a_superadmin_does():
    kb = ListingKB([_tenant_fact("mine", "bob", TENANT_A), _tenant_fact("theirs", "bob", TENANT_B)])
    admin = await visible_facts_page(kb, None, 10, 0, "adm", TENANT_A, [], AdminReadLedger())
    root = await visible_facts_page(kb, None, 10, 0, "root", TENANT_A, [], AdminReadLedger(), True)
    assert [f["fact_id"] for f in admin.facts] == ["mine"] and admin.total == 1
    assert root.total == 2


@pytest.mark.asyncio
async def test_a_failed_category_listing_is_unreadable_not_empty():
    class Failing(ListingKB):
        async def get_facts_in_category(self, *a, **kw):
            return {"success": False, "message": "boom"}

    with pytest.raises(RuntimeError):
        await visible_facts_page(Failing([]), "cat", 10, 0, ALICE, None, [], False)


@pytest.mark.asyncio
async def test_a_listing_of_exactly_the_scan_cap_is_not_truncated(monkeypatch):
    monkeypatch.setattr("api.knowledge_graph_facts.GRAPH_SCAN_LIMIT", SCAN_BATCH)
    exact = ListingKB([fact(f"f{i}", ALICE) for i in range(SCAN_BATCH)])
    more = ListingKB([fact(f"f{i}", ALICE) for i in range(SCAN_BATCH + 1)])
    assert (await visible_facts_page(exact, None, 5, 0, ALICE, None, [], False)).truncated is False
    assert (await visible_facts_page(more, None, 5, 0, ALICE, None, [], False)).truncated is True
    assert (await visible_facts_page(exact, "cat", 5, 0, ALICE, None, [], False)).truncated is False


@pytest.mark.asyncio
async def test_a_short_category_batch_does_not_end_the_scan():
    class Shortened(ListingKB):
        async def get_facts_in_category(self, category_id, include_descendants=False, limit=50, offset=0):
            got = await super().get_facts_in_category(category_id, include_descendants, limit, offset)
            if offset == 0:
                got["facts"] = got["facts"][1:]  # a deleted fact's hash is gone: the batch is short
            return got

    monkey_facts = [fact(f"f{i}", ALICE) for i in range(SCAN_BATCH + 3)]
    page = await visible_facts_page(Shortened(monkey_facts), "cat", 1000, 0, ALICE, None, [], False)
    assert page.total == SCAN_BATCH + 2


@pytest.mark.asyncio
async def test_a_quarantined_record_in_a_public_bucket_is_withheld():
    from autobot_shared.ssot_config import config

    quarantine = config.research_quarantine_collection
    client = await client_with({"autobot_docs": [("ok", {"k": "v"}), ("bad", {"collection": quarantine})]})
    built = await build_bucket_sections(client, viewer(), manager())
    assert [n["id"] for n in built["nodes"] if n["type"] == "bucket_record"] == ["bucket:autobot_docs:ok"]


def test_the_stored_chromadb_names_match_their_sections():
    assert section_for("company_tenant-a").key == "company"
    assert section_for("company_tenant-a_agents").key == "company"
    assert section_for("work_item_abc").key == "work_item"
    assert section_for("platform_template_kb").key == "memory"
    assert section_for("companyx") is None


def test_a_stored_company_collection_of_another_tenant_is_out_of_scope():
    admin = viewer(admin=True)
    assert collection_in_scope("tenant_admin", f"company_{TENANT_A}", admin)
    assert not collection_in_scope("tenant_admin", f"company_{TENANT_B}", admin)
    assert not collection_in_scope("tenant_admin", f"company_{TENANT_B}_agents", admin)


@pytest.mark.asyncio
async def test_a_summary_follows_its_source_fact():
    kb = ListingKB([fact("src-mine", ALICE), fact("src-bob", "bob")])
    records = {
        "knowledge_summaries": [
            ("s1", {"document_id": "src-mine"}),
            ("s2", {"document_id": "src-bob"}),
            ("s3", {"document_id": "deleted-fact"}),
        ]
    }
    client = await client_with(records)
    built = await build_bucket_sections(client, viewer(), manager(), kb=kb)
    assert [n["id"] for n in built["nodes"] if n["type"] == "bucket_record"] == ["bucket:knowledge_summaries:s1"]
    admin = await build_bucket_sections(client, viewer(admin=True), manager(), kb=kb)
    assert {n["id"] for n in admin["nodes"] if n["type"] == "bucket_record"} == {
        "bucket:knowledge_summaries:s1",
        "bucket:knowledge_summaries:s2",
    }, "an orphaned summary (deleted source) is withheld from an admin too"
    blind = await build_bucket_sections(client, viewer(admin=True), manager())
    assert blind["sections"] == [], "no KB to resolve sources: fail closed"


@pytest.mark.asyncio
async def test_code_records_of_a_source_the_viewer_may_not_read_are_withheld():
    async def authorize(source_id, user):
        if source_id == "private-repo":
            raise HTTPException(status_code=404, detail="Code source not found")

    client = await client_with(
        {
            "code_patterns": [
                ("own", {"source_id": "default"}),
                ("legacy", {"k": "v"}),
                ("open", {"source_id": "shared-repo"}),
                ("secret", {"source_id": "private-repo"}),
            ]
        }
    )
    with patch("api.codebase_analytics.endpoints.shared.authorize_source_access", new=AsyncMock(side_effect=authorize)):
        built = await build_bucket_sections(client, viewer(admin=True), manager())
    ids = {n["id"] for n in built["nodes"] if n["type"] == "bucket_record"}
    assert ids == {f"bucket:code_patterns:{i}" for i in ("own", "legacy", "open")}


@pytest.mark.asyncio
async def test_an_unavailable_source_registry_makes_the_collection_unreadable_not_public():
    async def down(source_id, user):
        raise HTTPException(status_code=503, detail="registry unavailable")

    client = await client_with({"code_patterns": [("x", {"source_id": "some-repo"})]})
    with patch("api.codebase_analytics.endpoints.shared.authorize_source_access", new=AsyncMock(side_effect=down)):
        built = await build_bucket_sections(client, viewer(), manager())
    assert built["sections"] == []


@pytest.mark.asyncio
async def test_a_truncated_scan_with_no_readable_row_is_still_reported(monkeypatch):
    monkeypatch.setattr("knowledge.graph_buckets.GRAPH_SCAN_LIMIT", 3)
    client = await client_with({"trajectories": [(f"t{i}", {"user_id": "bob"}) for i in range(5)]})
    built = await build_bucket_sections(client, viewer(), manager())
    (section,) = built["sections"]
    assert (section["total"], section["truncated"], section["limited"]) == (0, True, True)


@pytest.mark.asyncio
async def test_a_failing_preview_read_keeps_every_section():
    client = await client_with(
        {"trajectories": [("t", {"user_id": ALICE})], "autobot_memory": [("m", {"user_id": ALICE})]}
    )
    real = client.get_collection

    async def get_collection(name, *a, **kw):
        col = await real(name, *a, **kw)
        if name == "trajectories":
            col.get = AsyncMock(side_effect=[{"ids": ["t"], "metadatas": [{"user_id": ALICE}]}, RuntimeError("gone")])
        return col

    client.get_collection = get_collection
    built = await build_bucket_sections(client, viewer(), manager())
    assert {s["key"] for s in built["sections"]} == {"research", "memory"}
    names = {n["id"]: n["name"] for n in built["nodes"] if n["type"] == "bucket_record"}
    assert names["bucket:trajectories:t"] == "t", "falls back to the id"


async def _walk_by_cursor(kb, size, category=None, **who):
    seen, cursor = [], None
    while True:
        page = await visible_facts_page(kb, category, size, 0, ALICE, None, [], False, cursor=cursor or "0:0")
        seen.extend(f["fact_id"] for f in page.facts)
        cursor = page.cursor
        if cursor is None:
            return seen


@pytest.mark.asyncio
async def test_a_cursor_resumes_past_the_scan_cap_where_offset_alone_cannot(monkeypatch):
    monkeypatch.setattr("api.knowledge_graph_facts.GRAPH_SCAN_LIMIT", SCAN_BATCH)
    count = SCAN_BATCH * 2 + 70
    kb = ListingKB([fact(f"f{i:05d}", ALICE) for i in range(count)])
    control = await visible_facts_page(kb, None, 50, SCAN_BATCH + 20, ALICE, None, [], False)
    assert control.facts == [] and control.truncated, "offset alone never reaches a fact beyond the scan cap"
    first = await visible_facts_page(kb, None, 50, 0, ALICE, None, [], False)
    assert first.cursor == f"{SCAN_BATCH}:0", "the capped scan hands back where to resume"
    for category in (None, "cat"):
        seen = await _walk_by_cursor(kb, 50, category)
        assert seen == [f"f{i:05d}" for i in range(count)], "every readable fact once, in order, past the cap"


@pytest.mark.asyncio
async def test_a_cursor_page_ending_inside_a_batch_neither_repeats_nor_skips_a_fact():
    kb = ListingKB([fact(f"f{i:03d}", ALICE if i % 3 else "bob") for i in range(1300)])
    seen = await _walk_by_cursor(kb, 37)
    assert seen == [f"f{i:03d}" for i in range(1300) if i % 3]


@pytest.mark.asyncio
async def test_a_cursor_read_filters_by_permission_and_reports_more_only_while_a_cursor_returns():
    kb = ListingKB([fact("a", ALICE), fact("b", "bob"), fact("c", ALICE)])
    page = await visible_facts_page(kb, None, 1, 0, ALICE, None, [], False, cursor="0:0")
    assert [f["fact_id"] for f in page.facts] == ["a"] and page.cursor == "0:1" and page.total is None
    last = await visible_facts_page(kb, None, 5, 0, ALICE, None, [], False, cursor=page.cursor)
    assert [f["fact_id"] for f in last.facts] == ["c"] and last.cursor is None


def test_a_malformed_cursor_is_refused():
    from pydantic import ValidationError

    from api.knowledge_graph_facts import parse_cursor
    from api.schemas_knowledge_graph import GraphRequest

    assert parse_cursor("500:12") == (500, 12)
    with pytest.raises(ValidationError):
        GraphRequest(cursor="-1:0")
    with pytest.raises(ValidationError):
        GraphRequest(cursor="abc")


def _own_then_foreign(own, foreign):
    return ListingKB(
        [fact(f"mine{i}", ALICE) for i in range(own)] + [fact(f"theirs{i}", "bob") for i in range(foreign)]
    )


@pytest.mark.asyncio
async def test_no_next_page_is_promised_for_facts_only_another_owner_holds(monkeypatch):
    """The continuation probe reads through the permission filter, so it neither leaks nor promises a hidden page."""
    monkeypatch.setattr("api.knowledge_graph_facts.GRAPH_SCAN_LIMIT", SCAN_BATCH)
    kb = _own_then_foreign(3, SCAN_BATCH + 10)  # the cap ends inside another owner's facts, which go on past it
    first = await visible_facts_page(kb, None, 5, 0, ALICE, None, [], False)
    assert [f["fact_id"] for f in first.facts] == ["mine0", "mine1", "mine2"]
    assert first.truncated is False and first.cursor is None, "nothing readable is left past the cap"
    exact = await visible_facts_page(kb, None, 3, 0, ALICE, None, [], False, cursor="0:0")
    assert len(exact.facts) == 3 and exact.cursor is None, "a page filled by the last readable fact ends the listing"
    seen = await _walk_by_cursor(kb, 2)
    assert seen == ["mine0", "mine1", "mine2"], "no item of another owner on any page"
