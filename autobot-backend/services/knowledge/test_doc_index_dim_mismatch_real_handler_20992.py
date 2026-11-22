# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The REAL dimension-mismatch handler, driven through ``resolve_collection``, bumps the epoch (#20992).

``test_doc_index_dim_mismatch_invalidation`` stubs the indexer; here ``DocIndexerService`` is the real
class and only the Chroma client is faked, so ``_handle_dim_mismatch`` itself deletes the collection.
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.embedding_provenance import EmbeddingProvenance, provenance_to_metadata
from services.knowledge import doc_indexer
from services.knowledge.doc_index_orphans import resolve_collection
from services.knowledge.doc_indexer import AUTO_REINDEX_ON_DIM_MISMATCH_ENV, DocIndexerService

_BUMP = "knowledge.retrieval_invalidation.invalidate_retrieval_caches"
_REASON = "docs_collection_recreated"
_NAME = DocIndexerService.COLLECTION_NAME
_OLD_DIM, _NEW_DIM = 4, 8


class _Collection:
    def __init__(self, name: str, metadata: dict) -> None:
        self.name, self.metadata = name, metadata

    def count(self) -> int:
        return 1


class _Client:
    """Only the Chroma client surface the resolve path touches."""

    def __init__(self, dim: int) -> None:
        meta = {"hnsw:space": "cosine", **provenance_to_metadata(EmbeddingProvenance("old-model", dim))}
        self.collections = {_NAME: _Collection(_NAME, meta)}
        self.deleted: list[str] = []

    def list_collections(self):
        return list(self.collections.values())

    def delete_collection(self, name: str) -> None:
        self.deleted.append(name)
        del self.collections[name]

    def get_or_create_collection(self, name: str, metadata: dict | None = None):
        return self.collections.setdefault(name, _Collection(name, dict(metadata or {})))


def _indexer(stored_dim: int) -> tuple[DocIndexerService, _Client]:
    client = _Client(stored_dim)
    svc = DocIndexerService.__new__(DocIndexerService)  # real class, __init__ skipped (it builds clients)
    svc._client, svc._collection, svc._initialized, svc._needs_reindex = client, None, False, False
    return svc, client


@pytest.fixture
def auto_reindex(monkeypatch):
    monkeypatch.setenv(AUTO_REINDEX_ON_DIM_MISMATCH_ENV, "true")


@pytest.mark.asyncio
async def test_real_handler_recreates_and_bumps_the_epoch(auto_reindex):
    svc, client = _indexer(_OLD_DIM)
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        resolved = await resolve_collection(svc, "new-model", _NEW_DIM)
    assert client.deleted == [_NAME]  # the real _handle_dim_mismatch ran
    assert resolved is client.collections[_NAME]  # recreated at the new dimension
    assert svc._needs_reindex is True
    bump.assert_awaited_once_with(_REASON)


@pytest.mark.asyncio
async def test_matching_dimension_does_not_bump(auto_reindex):
    svc, client = _indexer(_NEW_DIM)
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        await resolve_collection(svc, "new-model", _NEW_DIM)
    assert client.deleted == []
    bump.assert_not_awaited()
    assert svc._needs_reindex is False


@pytest.mark.asyncio
async def test_flag_off_raises_without_deleting_or_bumping(monkeypatch):
    monkeypatch.delenv(AUTO_REINDEX_ON_DIM_MISMATCH_ENV, raising=False)
    svc, client = _indexer(_OLD_DIM)
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        with pytest.raises(Exception, match="dim"):
            await resolve_collection(svc, "new-model", _NEW_DIM)
    assert client.deleted == []
    bump.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_bump_does_not_depend_on_the_forced_reindex_finding_files(auto_reindex, tmp_path):
    svc, _ = _indexer(_OLD_DIM)
    svc._root_dir = tmp_path  # no documentation files under it
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        svc._collection = await resolve_collection(svc, "new-model", _NEW_DIM)
        svc._initialized = True
        with patch.object(doc_indexer, "_select_files", return_value=[]):
            result = await svc.index_all()
    assert result.total_files == 0
    bump.assert_awaited_once_with(_REASON)  # bumped at the recreate, not by the (empty) re-index
    assert svc._needs_reindex is True  # the empty run did not consume the forced re-index
