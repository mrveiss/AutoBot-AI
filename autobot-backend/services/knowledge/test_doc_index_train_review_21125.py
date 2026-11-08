# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Review fixes on the doc-index store guard and run record (#20886, train review)."""

import asyncio
import json
import logging
from pathlib import Path

import pytest

from knowledge.backends import InMemoryClient
from services.knowledge import doc_index_store_guard as guard
from services.knowledge import doc_indexer
from services.knowledge.doc_indexer import DocIndexerService

from .test_doc_indexer import _make_service
from .test_doc_indexer_populated_20886 import STORE, _Embedder


def test_a_nan_interval_falls_back_to_the_default() -> None:
    assert guard.clamp_progress_interval(float("nan")) == guard.DEFAULT_PROGRESS_INTERVAL_S


def test_a_failed_store_record_write_keeps_the_previous_record(tmp_path: Path, monkeypatch) -> None:
    override = tmp_path / "hashes.json"
    guard.write_recorded_store("old-store", override)
    real_replace = guard.os.replace
    monkeypatch.setattr(guard.Path, "write_text", lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        guard.write_recorded_store("new-store", override)
    monkeypatch.undo()
    assert guard.load_recorded_store(override) == "old-store"
    assert real_replace is guard.os.replace


def test_an_unreadable_final_count_does_not_lose_the_result(caplog) -> None:
    class _Broken:
        def count(self) -> int:
            raise ConnectionError("gone")

    result = doc_indexer.IndexResult(success=1)
    with caplog.at_level(logging.INFO):
        guard.log_run_summary(result, _Broken())
    assert "unknown vectors" in caplog.text


class _FailingEmbedder(_Embedder):
    def get_text_embedding(self, _text: str) -> list[float]:
        raise RuntimeError("embedding server down")


async def test_a_failed_document_is_not_cached(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    doc = root / "docs" / "a.md"
    await asyncio.to_thread(doc.write_text, "# A\n\n" + "alpha " * 80, encoding="utf-8")
    cache = tmp_path / "hashes.json"
    monkeypatch.setattr(doc_indexer, "HASH_CACHE_FILE", cache)
    monkeypatch.setattr(doc_indexer, "_select_files", lambda *_a, **_k: [(str(doc), 1)])
    svc = _make_service(root_dir=root)
    svc._llm_service = None
    svc._embed_model = _FailingEmbedder()
    svc._collection = InMemoryClient().get_or_create_collection("autobot_docs")
    svc._store = STORE
    svc._needs_reindex = False

    result = await DocIndexerService.index_all(svc)

    assert result.failed == 1
    saved = json.loads(await asyncio.to_thread(cache.read_text, encoding="utf-8")) if cache.exists() else {}
    assert "docs/a.md" not in saved
