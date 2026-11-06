# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A populated collection is never re-embedded; an unknown count or a moved store is refused (#20886)."""

import json
import logging
from pathlib import Path

import pytest

from knowledge.backends import InMemoryClient
from services.knowledge import doc_index_store_guard as guard
from services.knowledge import doc_indexer
from services.knowledge.doc_indexer import DocIndexerService

from .test_doc_indexer import _make_service

STORE = "http://chroma.example:8000"
OTHER = "/work/tree/data/chromadb"


class _Embedder:
    """Deterministic real embedder double: fixed-size vectors, counts its calls."""

    def __init__(self) -> None:
        self.calls = 0

    def get_text_embedding(self, _text: str) -> list[float]:
        self.calls += 1
        return [0.1] * 8


class _BrokenCount:
    def count(self) -> int:
        raise ConnectionError("store unreachable")


@pytest.fixture
def indexer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocIndexerService:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("# A\n\n" + "alpha " * 80, encoding="utf-8")
    monkeypatch.setattr(doc_indexer, "HASH_CACHE_FILE", tmp_path / "hashes.json")
    monkeypatch.setattr(doc_indexer, "_select_files", lambda *_a, **_k: [(str(root / "docs" / "a.md"), 1)])
    svc = _make_service(root_dir=root)
    svc._embed_model = _Embedder()
    svc._collection = InMemoryClient().get_or_create_collection("autobot_docs")
    svc._store = STORE
    svc._needs_reindex = False
    return svc


async def test_an_empty_collection_still_indexes(indexer: DocIndexerService) -> None:
    result = await indexer.index_all()
    assert result.success == 1
    assert indexer._collection.count() > 0


async def test_a_populated_collection_is_not_re_embedded(indexer: DocIndexerService, caplog) -> None:
    await indexer.index_all()
    embedded = indexer._embed_model.calls
    with caplog.at_level(logging.INFO):
        result = await indexer.index_all()
    assert indexer._embed_model.calls == embedded
    assert result.skipped == 1 and result.success == 0
    assert "Full reindex" not in caplog.text


async def test_the_reindex_trigger_is_logged_with_its_reason(indexer: DocIndexerService, caplog) -> None:
    with caplog.at_level(logging.INFO):
        await indexer.index_all()
    assert "Full reindex: collection count=0" in caplog.text
    assert "1/1" in caplog.text and "chunks=" in caplog.text  # per-file progress, AC 4
    assert "pid=" in caplog.text and "argv=" in caplog.text  # start line, AC 3


async def test_an_unreadable_count_is_never_read_as_empty(indexer: DocIndexerService) -> None:
    await indexer.index_all()
    embedded = indexer._embed_model.calls
    indexer._collection = _BrokenCount()
    result = await indexer.index_all()
    assert indexer._embed_model.calls == embedded
    assert "cannot read the collection's vector count" in result.errors[0]


async def test_an_empty_collection_in_a_moved_store_is_refused(indexer: DocIndexerService) -> None:
    await indexer.index_all()
    embedded = indexer._embed_model.calls
    indexer._collection = InMemoryClient().get_or_create_collection("autobot_docs")  # the wrong, empty store
    indexer._store = OTHER
    result = await indexer.index_all()
    assert indexer._embed_model.calls == embedded
    assert STORE in result.errors[0] and OTHER in result.errors[0]
    assert indexer._collection.count() == 0, "nothing was written to the other store"


async def test_force_re_embeds_into_a_moved_store_on_purpose(indexer: DocIndexerService) -> None:
    await indexer.index_all()
    indexer._collection = InMemoryClient().get_or_create_collection("autobot_docs")
    indexer._store = OTHER
    result = await indexer.index_all(force=True)
    assert result.success == 1 and indexer._collection.count() > 0
    assert guard.load_recorded_store(doc_indexer.HASH_CACHE_FILE) == OTHER


async def test_a_legacy_cache_without_a_recorded_store_keeps_the_old_behaviour(indexer: DocIndexerService) -> None:
    await indexer.index_all()
    guard.doc_index_store(doc_indexer.HASH_CACHE_FILE).unlink()
    indexer._collection = InMemoryClient().get_or_create_collection("autobot_docs")
    result = await indexer.index_all()
    assert result.success == 1


def test_the_store_record_is_written_beside_the_cache(indexer: DocIndexerService, tmp_path: Path) -> None:
    guard.save_recorded_store(STORE, doc_indexer.HASH_CACHE_FILE)
    assert json.loads((tmp_path / ".doc_index_store.json").read_text(encoding="utf-8")) == {"store": STORE}


def test_batch_progress_is_rate_limited(caplog) -> None:
    progress = guard.EmbedProgress(interval_s=3600)
    with caplog.at_level(logging.INFO):
        for _ in range(5):
            progress.tick()
    assert progress.count == 5 and "Doc indexer embedding" not in caplog.text


def test_embedding_requests_carry_a_caller_tag() -> None:
    assert guard.caller_tag()[guard.CALLER_HEADER].startswith("doc_indexer pid=")
