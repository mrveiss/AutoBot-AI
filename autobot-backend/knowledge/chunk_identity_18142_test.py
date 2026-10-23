# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One chunk identity: precedence, and a graph node joining to its vector chunk (#18142)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from knowledge.chunk_identity import (
    DOC_SEARCH_SOURCE,
    DOC_SOURCE,
    SEED_SOURCE,
    STORE_ID_KEY,
    doc_chunk_id,
    legacy_chunk_id,
    resolve_chunk_id,
    seed_chunk_id,
    stamp_chunk_id,
)
from services.knowledge.doc_indexer import DocIndexerService
from services.knowledge.test_doc_indexer import _make_service

REL = "docs/x.md"
SECTION = "Setup"


def _doc_meta(**extra: Any) -> dict:
    return {"source": DOC_SOURCE, "file_path": REL, "section": SECTION, "chunk_index": 2, **extra}


class _Collection:
    """The part of a Chroma collection a join reads: rows keyed by their store id."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def upsert(self, ids, embeddings=None, documents=None, metadatas=None) -> None:
        for i, m in zip(ids, metadatas):
            self.rows[i] = m


def _hit(store_id: str, meta: dict) -> SimpleNamespace:
    """A search hit as a retriever sees it: metadata and a file path, never the store id itself."""
    return SimpleNamespace(metadata=dict(meta), source_path=meta.get("file_path", ""))


# --- precedence: each pair differs in exactly one rung, so the order is what decides -------------


def test_stored_metadata_id_beats_top_level_id() -> None:
    assert resolve_chunk_id({"metadata": {"chunk_id": "m"}, "chunk_id": "t"}) == "m"
    assert resolve_chunk_id({"metadata": {}, "chunk_id": "t"}) == "t"


def test_top_level_id_beats_the_rebuilt_legacy_id() -> None:
    assert resolve_chunk_id({"metadata": _doc_meta(), "chunk_id": "t"}) == "t"
    assert resolve_chunk_id({"metadata": _doc_meta()}) == doc_chunk_id(REL, SECTION, 2)


def test_rebuilt_legacy_id_beats_source_path() -> None:
    legacy = {"metadata": _doc_meta(), "source_path": REL}
    assert resolve_chunk_id(legacy) == doc_chunk_id(REL, SECTION, 2)
    assert resolve_chunk_id({"metadata": {}, "source_path": REL}) == REL


def test_nothing_known_is_the_empty_string() -> None:
    assert resolve_chunk_id({}) == ""
    assert resolve_chunk_id(SimpleNamespace()) == ""


def test_dict_and_object_results_resolve_alike() -> None:
    meta = _doc_meta()
    assert resolve_chunk_id({"metadata": meta, "source_path": REL}) == resolve_chunk_id(
        SimpleNamespace(metadata=meta, source_path=REL)
    )
    stored = _doc_meta(chunk_id="abc")
    assert resolve_chunk_id(SimpleNamespace(metadata=stored, source_path=REL)) == "abc"


def test_two_chunks_of_one_file_no_longer_collapse() -> None:
    """The old source_path fallback gave every chunk of a file the same id."""
    a = resolve_chunk_id({"metadata": _doc_meta(chunk_index=0), "source_path": REL})
    b = resolve_chunk_id({"metadata": _doc_meta(chunk_index=1), "source_path": REL})
    assert a != b


def test_legacy_id_needs_the_whole_recipe() -> None:
    assert legacy_chunk_id({"source": DOC_SOURCE, "file_path": REL}) == ""
    assert legacy_chunk_id({"source": "elsewhere", "file_path": REL, "section": "s", "chunk_index": 0}) == ""
    seed = {"source": SEED_SOURCE, "seed_collection": "c", "relative_path": "a.md", "chunk_index": "3"}
    assert legacy_chunk_id(seed) == seed_chunk_id("c", "a.md", 3)


def test_stamp_does_not_mutate_its_input() -> None:
    meta = {"a": 1}
    assert stamp_chunk_id(meta, "x") == {"a": 1, "chunk_id": "x"}
    assert meta == {"a": 1}


# --- the join: graph node (keyed by the canonical id) -> vector chunk -----------------------------


def _vector_index(collection: _Collection) -> dict[str, dict]:
    """Vector chunks keyed by the canonical id a reader derives from them."""
    return {resolve_chunk_id(_hit(i, m)): m for i, m in collection.rows.items()}


def test_new_chunk_joins_through_its_stored_id() -> None:
    svc = _make_service()
    svc._collection = _Collection()
    meta = {"source": DOC_SOURCE, "file_path": REL, "section": SECTION, "chunk_index": 2}
    DocIndexerService._embed_and_upsert(svc, "body", doc_chunk_id(REL, SECTION, 2), meta)
    (store_id,) = svc._collection.rows
    assert svc._collection.rows[store_id]["chunk_id"] == store_id
    graph_node_id = store_id  # the mesh node is keyed on the chunk's id
    assert _vector_index(svc._collection)[graph_node_id]["file_path"] == REL


def test_oversize_split_pieces_each_store_their_own_id() -> None:
    svc = _make_service()
    svc._collection = _Collection()
    parent = doc_chunk_id(REL, SECTION, 0)
    DocIndexerService._embed_and_upsert(svc, "left", f"{parent}_L0", {"chunk_id_parent": parent})
    assert svc._collection.rows[f"{parent}_L0"]["chunk_id"] == f"{parent}_L0"


def test_legacy_chunk_joins_through_the_fallback_without_a_rewrite() -> None:
    collection = _Collection()
    legacy_store_id = doc_chunk_id(REL, SECTION, 2)  # what the old indexer used as the Chroma id
    collection.rows[legacy_store_id] = _doc_meta()  # ...and did not store
    assert "chunk_id" not in collection.rows[legacy_store_id]
    assert _vector_index(collection)[legacy_store_id] is collection.rows[legacy_store_id]
    assert "chunk_id" not in collection.rows[legacy_store_id], "the resolver must not write"


def test_a_reindexed_legacy_chunk_keeps_its_node() -> None:
    legacy = _doc_meta()
    reindexed = stamp_chunk_id(legacy, doc_chunk_id(REL, SECTION, 2))
    assert resolve_chunk_id(_hit("", legacy)) == resolve_chunk_id(_hit("", reindexed))


@pytest.mark.parametrize("seeded", [True, False])
def test_seed_chunk_joins_stored_or_legacy(seeded: bool) -> None:
    meta = {"source": SEED_SOURCE, "seed_collection": "c", "relative_path": "a.md", "chunk_index": 1}
    cid = seed_chunk_id("c", "a.md", 1)
    if seeded:
        meta = stamp_chunk_id(meta, cid)
    assert resolve_chunk_id({"metadata": meta, "source_path": "a.md"}) == cid


# Literal pins (#18142 review): every other test compares the helper with itself, so an edit to
# the key format or the prefix length would pass while orphaning every stored KB id. These
# values were computed from main's pre-#18142 formulas (doc_index_orphans.chunk_base_id,
# cognition_seeder._chunk_id) with hashlib alone, not through this module.
@pytest.mark.parametrize(
    ("chunk_id", "expected"),
    [
        (lambda: doc_chunk_id("docs/x.md", "Setup", 2), "72446a68c458"),
        (lambda: seed_chunk_id("cognition", "docs/y.md", 3), "11e94f5e85d881bd"),
    ],
    ids=["doc", "seed"],
)
def test_stored_ids_keep_their_pre_18142_values(chunk_id, expected: str) -> None:
    assert chunk_id() == expected


def test_the_carried_store_id_beats_the_top_level_id_and_the_rebuilt_id() -> None:
    meta = _doc_meta(**{STORE_ID_KEY: "store-row"})
    assert resolve_chunk_id({"metadata": meta, "chunk_id": "top"}) == "store-row"
    assert resolve_chunk_id({"metadata": {**meta, "chunk_id": "stamped"}}) == "stamped"


def test_the_search_relabelled_source_still_rebuilds_the_doc_id() -> None:
    meta = _doc_meta(source=DOC_SEARCH_SOURCE)
    assert resolve_chunk_id({"metadata": meta, "source_path": REL}) == "72446a68c458"


# --- through DocIndexerService.search, on rows exactly as an old indexer left them (#19149) --------


async def _search(rows: list[tuple[str, dict]]) -> list[Any]:
    svc = _make_service(collection_count=len(rows))
    svc._collection.query = MagicMock(
        return_value={
            "ids": [[i for i, _ in rows]],
            "documents": [["body"] * len(rows)],
            "metadatas": [[dict(m) for _, m in rows]],
            "distances": [[0.1] * len(rows)],
        }
    )
    stub = MagicMock(RankedResult=lambda **kw: SimpleNamespace(**kw))
    with patch.dict("sys.modules", {"advanced_rag_optimizer": stub}):
        return await svc.search("q", n_results=len(rows))


@pytest.mark.asyncio
async def test_unstamped_doc_chunks_of_one_file_keep_distinct_ids_through_search() -> None:
    rows = [(doc_chunk_id(REL, SECTION, i), _doc_meta(chunk_index=i)) for i in range(3)]
    hits = await _search(rows)
    assert all(h.metadata["source"] == DOC_SEARCH_SOURCE for h in hits)
    assert [resolve_chunk_id(h) for h in hits] == [i for i, _ in rows]
    assert resolve_chunk_id(hits[2]) == "72446a68c458"  # literal pin: docs/x.md / Setup / 2


@pytest.mark.asyncio
async def test_unstamped_split_siblings_resolve_to_their_stored_ids_through_search() -> None:
    parent = doc_chunk_id(REL, SECTION, 2)
    legacy = _doc_meta(chunk_id_parent=parent, split_depth=0)  # equal metadata: only the row id differs
    hits = await _search([(f"{parent}_L0", legacy), (f"{parent}_R0", legacy)])
    assert [resolve_chunk_id(h) for h in hits] == ["72446a68c458_L0", "72446a68c458_R0"]  # literal pins


@pytest.mark.asyncio
async def test_a_stamped_row_keeps_its_stamp_through_search() -> None:
    hits = await _search([("row", _doc_meta(chunk_id="stamped"))])
    assert resolve_chunk_id(hits[0]) == "stamped"
