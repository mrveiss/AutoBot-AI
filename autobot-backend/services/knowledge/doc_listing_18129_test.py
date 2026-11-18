# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The documentation browser reads the collection the one indexer writes (#18129).

The retired standalone indexer mirrored a ``doc_hash:*`` Redis entry per file and the browser
scanned those keys. Nothing writes them any more, so a browser still reading Redis is empty on a
fresh install; these tests pin that the three endpoints read the ``autobot_docs`` collection.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import knowledge as api
from api.schemas_knowledge import DocsBrowseRequest
from services.knowledge.doc_indexer import DocIndexerService
from services.knowledge.doc_listing import group_indexed_documents, list_indexed_documents
from services.knowledge.test_doc_indexer import _make_service


def _meta(path: str, title: str, at: str, i: int = 0) -> dict:
    return {"file_path": path, "title": title, "indexed_at": at, "doc_type": "markdown", "tier": "1", "chunk_index": i}


ROWS = [
    _meta("docs/api/a.md", "A", "2026-10-01T00:00:00", 0),
    _meta("docs/api/a.md", "A", "2026-10-03T00:00:00", 1),
    _meta("docs/developer/b.md", "B", "2026-10-02T00:00:00"),
]


class _FakeCollection:
    """Just enough of a Chroma collection for ``get_all_paginated``, the stale-chunk read and its delete."""

    def __init__(self, metadatas: list[dict]) -> None:
        self.metadatas = list(metadatas)
        self.ids = [f"id{i}" for i in range(len(self.metadatas))]

    def get(self, where=None, limit=None, offset=0, include=None) -> dict:
        rows = [
            (i, m)
            for i, m in zip(self.ids, self.metadatas)
            if not where or all(m.get(k) == v for k, v in where.items())
        ]
        page = rows[offset : None if limit is None else offset + limit]
        return {"ids": [i for i, _ in page], "metadatas": [m for _, m in page]}

    def delete(self, where=None, ids=None) -> None:
        keep = [
            (i, m)
            for i, m in zip(self.ids, self.metadatas)
            if (ids is not None and i not in ids)
            or (where is not None and not all(m.get(k) == v for k, v in where.items()))
        ]
        self.ids = [i for i, _ in keep]
        self.metadatas = [m for _, m in keep]

    def upsert(self, ids, embeddings=None, documents=None, metadatas=None) -> None:
        for i, m in zip(ids, metadatas):
            if i in self.ids:
                self.metadatas[self.ids.index(i)] = m
            else:
                self.ids.append(i)
                self.metadatas.append(m)


def _service(rows: list[dict], initialized: bool = True) -> MagicMock:
    service = MagicMock()
    service._initialized = initialized
    service._collection = _FakeCollection(rows)
    service.initialize = AsyncMock(return_value=initialized)
    return service


def _indexed(rows):
    return patch("services.knowledge.doc_indexer.get_doc_indexer_service", return_value=_service(rows))


def test_chunks_group_into_one_entry_per_document() -> None:
    docs = {d["file_path"]: d for d in group_indexed_documents(ROWS)}
    assert set(docs) == {"docs/api/a.md", "docs/developer/b.md"}
    a = docs["docs/api/a.md"]
    assert (a["chunks"], a["indexed_at"], a["category"]) == (2, "2026-10-03T00:00:00", "api")
    assert docs["docs/developer/b.md"]["category"] == "developer"
    assert len({d["content_hash"] for d in docs.values()}) == 2


def test_the_old_redis_reader_is_empty_without_doc_hash_keys_the_collection_reader_is_not() -> None:
    """Contrast: the retired reader scanned ``doc_hash:*``; only the retired indexer wrote them."""

    def retired_redis_reader(redis) -> list:
        keys = redis.scan_iter(match="doc_hash:*")
        return [json.loads(redis.get(k)) for k in keys]

    redis = MagicMock()
    redis.scan_iter.return_value = []  # a fresh install: DocIndexerService wrote no doc_hash keys
    assert retired_redis_reader(redis) == []
    docs = asyncio.run(list_indexed_documents(_service(ROWS)))
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_browse_filters_sorts_and_paginates_the_collection() -> None:
    with _indexed(ROWS):
        out = await api.browse_documentation(admin_check=True, request=DocsBrowseRequest(category="api"), req=None)
    assert out["success"] is True
    assert [d["file_path"] for d in out["documents"]] == ["docs/api/a.md"]
    assert out["pagination"]["total_documents"] == 1
    assert out["documents"][0]["content_hash"]


@pytest.mark.asyncio
async def test_categories_count_documents_by_taxonomy_category() -> None:
    with _indexed(ROWS):
        out = await api.get_documentation_categories(admin_check=True, req=None)
    assert out["total_documents"] == 2
    assert {c["id"]: c["count"] for c in out["categories"]} == {"api": 1, "developer": 1}


@pytest.mark.asyncio
async def test_stats_come_from_chunk_metadata() -> None:
    with _indexed(ROWS):
        out = await api.get_documentation_stats(admin_check=True, req=None)
    stats = out["stats"]
    assert (stats["total_documents"], stats["total_chunks"], stats["categories_count"]) == (2, 3, 2)
    assert stats["latest_indexed"] == "2026-10-03T00:00:00"


@pytest.mark.asyncio
async def test_an_unreachable_index_is_a_503_not_an_empty_browser() -> None:
    with patch("services.knowledge.doc_indexer.get_doc_indexer_service", return_value=_service([], initialized=False)):
        with pytest.raises(HTTPException) as exc:
            await api.get_documentation_stats(admin_check=True, req=None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_reindexing_a_file_drops_its_prior_chunks_even_when_a_section_was_renamed() -> None:
    svc: DocIndexerService = _make_service()
    svc._collection = _FakeCollection([{**_meta("docs/x.md", "X", "t"), "section": "Old name"}])
    other = {**_meta("docs/other.md", "O", "t"), "section": "Keep"}
    svc._collection.metadatas.append(other)
    body = "# X\n\n## New name\n\n" + "words " * 80
    await svc._index_file_chunks("/repo/docs/x.md", body, "docs/x.md", 1)
    remaining = [m for m in svc._collection.metadatas if m["file_path"] == "docs/x.md"]
    assert remaining == [], "the renamed section's old chunk must not survive the re-index"
    assert other in svc._collection.metadatas
