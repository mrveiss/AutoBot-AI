# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A facts cursor is resumed within the per-request skip budget, never by an unbounded skip (#20945)."""

import pytest

from api.knowledge_graph_facts import RESUME_POSITION_LIMIT, visible_facts_page
from api.knowledge_graph_sections import facts_section
from tests.fixtures.graph_buckets_fakes_20945 import ALICE, ListingKB, fact

LIMIT, BATCH = 8, 4


@pytest.fixture(autouse=True)
def _small_budget(monkeypatch):
    monkeypatch.setattr("api.knowledge_graph_facts.SCAN_BATCH", BATCH)
    monkeypatch.setattr("api.knowledge_graph_facts.RESUME_POSITION_LIMIT", LIMIT)


async def _page(kb, cursor, size=2):
    return await visible_facts_page(kb, None, size, 0, ALICE, None, [], False, cursor=cursor)


def test_the_default_budget_covers_a_first_page_scan():
    assert RESUME_POSITION_LIMIT >= 100


@pytest.mark.asyncio
async def test_a_cursor_past_the_budget_reads_nothing_and_reports_the_budget_exhausted():
    kb = ListingKB([fact(f"f{i}", ALICE) for i in range(30)])
    page = await _page(kb, "999999999:0")
    assert kb.calls == [], "no listing is read for a cursor beyond the budget"
    assert page.facts == [] and page.cursor is None and page.budget_exhausted is True
    section = facts_section(page, 0)
    assert section["budget_exhausted"] is True and section["limited"] is True and section["cursor"] is None


@pytest.mark.asyncio
async def test_a_page_whose_continuation_lies_past_the_budget_ends_with_the_flag_not_a_cursor():
    kb = ListingKB([fact(f"f{i}", ALICE) for i in range(40)])
    page = await _page(kb, f"{LIMIT}:0", size=BATCH)
    assert [f["fact_id"] for f in page.facts] == [f"f{i}" for i in range(LIMIT, LIMIT + BATCH)]
    assert page.cursor is None and page.budget_exhausted is True


@pytest.mark.asyncio
async def test_a_cursor_within_the_budget_still_continues():
    kb = ListingKB([fact(f"f{i}", ALICE) for i in range(40)])
    page = await _page(kb, f"{BATCH}:0", size=2)
    assert [f["fact_id"] for f in page.facts] == ["f4", "f5"]
    assert page.cursor == f"{BATCH}:2" and page.budget_exhausted is False
