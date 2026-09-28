# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/tests/services/test_kb_collection_routing_17533.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A watched folder's collection NAME resolves to the id the store is keyed by (#17533).

Collections are keyed by a UUID minted at creation; `WatchFolderConfig.collection` is
user-authored text. Nothing joined the two, so a watched folder never reached the
collection it named — the write landed, the membership did not, and the only signal was
a metadata field carrying a name the store does not use.

**The policy is refuse, never create** (owner ruling, 2026-09-28). A typo in a config
string would otherwise mint a durable collection and ingest into it, with nothing marking
it unintended. These tests exist mostly to keep that property: the interesting assertions
are the ones that fail if an unknown name ever starts creating something.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from services.kb_watch_ingest import ingest_stored, ingest_watched_file, resolve_collection_id

CONFIG = SimpleNamespace(category="uploads", tags=["manual"], collection="Research Notes")
FILE = Path("/watched/report.txt")


class _KB:
    """Only what the resolver and the ingest touch, with the real return shapes."""

    def __init__(self, pages, add_result=None):
        self._pages = pages
        self.listed = []
        self.added = []
        self.created = []
        self._add_result = add_result or {"status": "success", "fact_id": "f1"}

    async def list_collections(self, limit=100, offset=0, sort_by="name"):
        self.listed.append((limit, offset))
        return self._pages[len(self.listed) - 1]

    async def add_document(self, content, metadata=None, doc_id=None):
        self.added.append(metadata)
        return self._add_result

    async def create_collection(self, *a, **k):  # pragma: no cover - must never be called
        self.created.append((a, k))
        raise AssertionError("resolution must never create a collection (#17533 ruling)")


def _page(collections, has_more=False, success=True, message=None):
    page = {"success": success, "collections": collections, "has_more": has_more}
    if message:
        page["message"] = message
    return page


@pytest.fixture
def kb(monkeypatch):
    def _install(instance):
        import knowledge

        async def _get():
            return instance

        monkeypatch.setattr(knowledge, "get_knowledge_base", _get, raising=False)
        return instance

    return _install


# ---------------------------------------------------------------------------
# resolve_collection_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_known_name_resolves_to_its_id(kb):
    kb(_KB([_page([{"id": "uuid-1", "name": "Research Notes"}])]))

    result = await resolve_collection_id("Research Notes")

    assert result["status"] == "resolved"
    assert result["collection_id"] == "uuid-1"


@pytest.mark.asyncio
async def test_an_unknown_name_is_refused_and_nothing_is_created(kb):
    """The ruling, as an assertion. `_KB.create_collection` raises if reached."""
    store = kb(_KB([_page([{"id": "uuid-1", "name": "Research Notes"}])]))

    result = await resolve_collection_id("Reserch Notes")

    assert result["status"] == "not_found"
    assert store.created == []


@pytest.mark.asyncio
async def test_the_refusal_names_what_does_exist(kb):
    """A refusal an operator cannot act on is barely better than a silent drop.

    The misspelling is the expected case — this message is what turns it into a
    five-second fix instead of an investigation.
    """
    kb(_KB([_page([{"id": "a", "name": "Research Notes"}, {"id": "b", "name": "Meeting Minutes"}])]))

    result = await resolve_collection_id("Reserch Notes")

    assert "Reserch Notes" in result["message"]
    assert "Research Notes" in result["message"] and "Meeting Minutes" in result["message"]


@pytest.mark.asyncio
async def test_resolution_pages_past_the_first_hundred(kb):
    """`list_collections` defaults to 100 per page. A folder naming the 101st collection
    must not be told it does not exist — the bounded-scan trap of #17713, avoided here
    rather than inherited."""
    store = kb(
        _KB(
            [
                _page([{"id": f"id-{i}", "name": f"c{i}"} for i in range(100)], has_more=True),
                _page([{"id": "id-target", "name": "Research Notes"}], has_more=False),
            ]
        )
    )

    result = await resolve_collection_id("Research Notes")

    assert result["status"] == "resolved"
    assert result["collection_id"] == "id-target"
    assert store.listed == [(100, 0), (100, 100)], "it must ask for the second page"


@pytest.mark.asyncio
async def test_a_listing_failure_is_an_error_not_a_missing_collection(kb):
    """`could not look` and `looked, not there` have different remedies.

    Reported as `error` so a Redis outage does not read as a misspelled config, which
    would send an operator to fix the wrong thing.
    """
    kb(_KB([_page([], success=False, message="Redis not available")]))

    result = await resolve_collection_id("Research Notes")

    assert result["status"] == "error"
    assert "Redis not available" in result["message"]


@pytest.mark.asyncio
async def test_an_empty_configured_name_is_an_error_before_any_lookup(kb):
    store = kb(_KB([]))

    result = await resolve_collection_id("   ")

    assert result["status"] == "error"
    assert store.listed == [], "an unconfigured collection needs no round trip"


# ---------------------------------------------------------------------------
# the ingest path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_resolvable_collection_is_stored_as_its_id_with_the_name_beside_it(kb):
    store = kb(_KB([_page([{"id": "uuid-1", "name": "Research Notes"}])]))

    result = await ingest_watched_file("f1", CONFIG, FILE, "some text")

    assert ingest_stored(result)
    metadata = store.added[0]
    assert metadata["collection"] == "uuid-1", "the store is keyed by id"
    assert metadata["collection_name"] == "Research Notes", "the human-readable name survives"


@pytest.mark.asyncio
async def test_an_unresolvable_collection_refuses_the_write_entirely(kb):
    """Not a partial store. The transcript of #17022 was stored-but-unrouted by design;
    a watched file whose folder is misconfigured is a configuration error, and writing it
    into no collection would leave an orphan nobody asked for."""
    store = kb(_KB([_page([{"id": "uuid-1", "name": "Research Notes"}])]))
    bad = SimpleNamespace(category="uploads", tags=[], collection="Nope")

    result = await ingest_watched_file("f1", bad, FILE, "some text")

    assert not ingest_stored(result), "a refusal must not read as a write"
    assert result["status"] == "rejected"
    assert result["collection_status"] == "not_found"
    assert store.added == [], "nothing may be written when routing failed"


@pytest.mark.asyncio
async def test_the_rejection_reaches_the_watcher_error_surface(kb, monkeypatch):
    """The operator-visible half of the ruling.

    `_record_error` writes `last_error`, which `get_watch_folders()` returns and
    `GET /watch-folders` serves — so the refusal reaches a person rather than a log
    level nobody reads. A watch folder silently dropping every file because of a typo
    is the same defect as the watcher that silently dropped modifications (#17547).
    """
    from services.kb_folder_watcher import KBFolderWatcherService

    service = KBFolderWatcherService.__new__(KBFolderWatcherService)
    service._stats = {"f1": {"files_ingested": 0, "errors": 0}}
    service._record_error("f1", "collection routing failed: no collection is named 'Nope'")

    assert service._stats["f1"]["errors"] == 1
    assert "Nope" in service._stats["f1"]["last_error"]


@pytest.mark.asyncio
async def test_resolution_runs_before_the_write_so_a_failure_costs_nothing(kb):
    """Ordering, asserted because it is the difference between a refused write and a
    write that has to be undone."""
    store = kb(_KB([_page([], success=False, message="Redis not available")]))

    await ingest_watched_file("f1", CONFIG, FILE, "some text")

    assert store.added == []
