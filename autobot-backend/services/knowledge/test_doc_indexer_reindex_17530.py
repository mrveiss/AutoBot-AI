# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A re-index drops stale chunks only after the new ones are stored; categories use the relative path (#17530)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.knowledge.doc_index_orphans import chunk_base_id
from services.knowledge.doc_indexer import _select_files

from .doc_listing_18129_test import _FakeCollection
from .test_doc_indexer import _make_service

REL = "docs/x.md"
BODY = "# X\n\n## New name\n\n" + "words " * 80


def _service(old_sections):
    svc = _make_service()
    old = [{"file_path": REL, "section": s, "index_run": "old"} for s in old_sections]
    svc._collection = _FakeCollection(old)
    svc._collection.ids = [chunk_base_id(REL, s, 0) for s in old_sections]
    return svc


@pytest.mark.asyncio
async def test_a_failing_embed_keeps_the_old_rows() -> None:
    svc = _service(["New name"])
    before = list(svc._collection.ids)
    svc._embed_model.get_text_embedding = MagicMock(side_effect=RuntimeError("embed down"))
    await svc._index_file_chunks("/repo/" + REL, BODY, REL, 1)
    assert svc._collection.ids == before, "a failed embed must not cost the file its old rows"


@pytest.mark.asyncio
async def test_a_good_reindex_removes_only_the_orphans() -> None:
    svc = _service(["New name", "Old name"])
    await svc._index_file_chunks("/repo/" + REL, BODY, REL, 1)
    kept = svc._collection.ids
    assert chunk_base_id(REL, "Old name", 0) not in kept
    assert chunk_base_id(REL, "New name", 0) in kept
    assert {m["index_run"] for m in svc._collection.metadatas} != {"old"}


def test_category_ignores_the_checkout_root(tmp_path: Path) -> None:
    root = tmp_path / "api" / "checkout"
    (root / "docs" / "features").mkdir(parents=True)
    (root / "docs" / "features" / "f.md").write_text("# F\n", encoding="utf-8")
    assert _select_files(root, category="api") == []
    assert [Path(p).name for p, _ in _select_files(root, category="features")] == ["f.md"]
