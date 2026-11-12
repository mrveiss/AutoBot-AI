# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Walking the graph's facts by cursor returns every readable fact exactly once (#20945).

The listing is the real ``stream_facts`` / ``collect_facts`` / ``apply_quarantine`` chain ``get_all_facts``
runs, over fake Redis rows with hidden (another owner's), quarantined and readable facts interleaved.
"""

import itertools

import pytest

from api.knowledge_graph_facts import visible_facts_page
from autobot_shared.ssot_config import config
from knowledge.fact_stream import collect_facts, stream_facts
from knowledge.quarantine import apply_quarantine
from tests.fixtures.graph_buckets_fakes_20945 import ALICE, manager

BATCH, CAP = 4, 12


class _Pipe:
    def __init__(self, rows):
        self.rows, self.keys = rows, []

    def hgetall(self, key):
        self.keys.append(key)

    async def execute(self):
        return [self.rows[key] for key in self.keys]


class _Redis:
    def __init__(self, rows):
        self.rows = rows

    async def scan_iter(self, match=None, count=None):
        for key in self.rows:
            yield key

    def pipeline(self):
        return _Pipe(self.rows)


class StreamKB:
    """``get_all_facts`` as ``knowledge/facts.py`` composes it: quarantine dropped while streaming."""

    def __init__(self, rows):
        self.redis = _Redis(rows)
        self.ownership_manager = manager()
        self.listings = []

    async def get_all_facts(self, limit=None, offset=0):
        self.listings.append((limit, offset))
        process = lambda key, row, _collection: {"fact_id": key, "content": "", "metadata": row}  # noqa: E731
        facts = await collect_facts(stream_facts(self.redis, process, None, False, batch_size=3), offset, limit)
        return await apply_quarantine(facts, False, None)


def _rows(count):
    """Every 3rd fact is another owner's, every 5th (offset 2) is quarantined; the rest alice may read."""
    rows = {}
    for i in range(count):
        meta = {"owner_id": "bob" if i % 3 == 0 else ALICE, "visibility": "private"}
        if i % 5 == 2:
            meta["collection"] = config.research_quarantine_collection
        rows[f"f{i:03d}"] = meta
    return rows


def _readable(rows):
    return [k for k, m in rows.items() if m["owner_id"] == ALICE and "collection" not in m]


async def _walk(kb, size):
    """The first page from the start, then every continuation: ``(ids in order, pages)``."""
    seen, pages, cursor = [], [], None
    while True:
        page = await visible_facts_page(kb, None, size, 0, ALICE, None, [], False, cursor=cursor)
        pages.append(page)
        seen.extend(f["fact_id"] for f in page.facts)
        cursor = page.cursor
        if cursor is None:
            return seen, pages
        assert len(pages) < 200, "the walk must end"


@pytest.fixture(autouse=True)
def _small_scan(monkeypatch):
    monkeypatch.setattr("api.knowledge_graph_facts.SCAN_BATCH", BATCH)
    monkeypatch.setattr("api.knowledge_graph_facts.GRAPH_SCAN_LIMIT", CAP)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "count,size",
    list(itertools.product((0, 1, BATCH, BATCH + 1, CAP - 1, CAP, CAP + 1, 2 * CAP + 3), (1, 2, 3, 5, BATCH, CAP))),
)
async def test_walking_by_cursor_returns_every_readable_fact_exactly_once(count, size):
    rows = _rows(count)
    seen, pages = await _walk(StreamKB(rows), size)
    assert seen == _readable(rows), "no readable fact skipped, repeated or reordered"
    assert pages[-1].cursor is None and all(p.cursor is not None for p in pages[:-1])


@pytest.mark.asyncio
async def test_the_first_page_below_the_cap_offers_the_rest_of_the_visible_facts():
    rows = _rows(CAP - 2)  # fewer raw records than the scan cap, more readable facts than the page
    page = await visible_facts_page(StreamKB(rows), None, 2, 0, ALICE, None, [], False)
    assert [f["fact_id"] for f in page.facts] == _readable(rows)[:2]
    assert page.cursor is not None and page.truncated is False and page.total == len(_readable(rows))


@pytest.mark.asyncio
async def test_the_cap_cursor_points_after_the_last_returned_fact_not_after_the_scan():
    rows = _rows(3 * CAP)
    page = await visible_facts_page(StreamKB(rows), None, 2, 0, ALICE, None, [], False)
    follow = await visible_facts_page(StreamKB(rows), None, 2, 0, ALICE, None, [], False, cursor=page.cursor)
    assert [f["fact_id"] for f in follow.facts] == _readable(rows)[2:4], "the facts between page and cap stay reachable"


@pytest.mark.asyncio
async def test_a_batch_with_quarantined_facts_in_the_middle_is_not_read_as_the_end():
    rows = _rows(CAP)  # a full raw batch of listed facts comes back full: quarantine never shortens it
    kb = StreamKB(rows)
    batch = await kb.get_all_facts(limit=BATCH, offset=0)
    assert len(batch) == BATCH and all("collection" not in f["metadata"] for f in batch)
    nxt = await kb.get_all_facts(limit=BATCH, offset=BATCH)
    assert [f["fact_id"] for f in batch + nxt] == [k for k, m in rows.items() if "collection" not in m][: 2 * BATCH]
