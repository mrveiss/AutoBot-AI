# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dimension-mismatch recreate invalidates cached retrievals (#20992).

``_handle_dim_mismatch`` runs in a worker thread, so ``resolve_collection`` awaits the
invalidation after it. The bump must not depend on how many files the re-index later finds.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.knowledge.doc_index_orphans import resolve_collection

_BUMP = "knowledge.retrieval_invalidation.invalidate_retrieval_caches"
_REASON = "docs_collection_recreated"


class _Indexer:
    """Stands in for DocIndexerService: the resolve either recreates (sets the flag) or not."""

    def __init__(self, recreate: bool, fail: bool = False, needs_reindex: bool = False) -> None:
        self._needs_reindex = needs_reindex
        self._recreate = recreate
        self._fail = fail

    def _resolve_collection(self, model_name, embed_dim):
        if self._recreate:
            self._needs_reindex = True
        if self._fail:
            raise RuntimeError("create failed")
        return ("collection", model_name, embed_dim)


@pytest.mark.asyncio
async def test_a_recreate_bumps_the_epoch_and_keeps_the_reindex_flag():
    indexer = _Indexer(recreate=True)
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        assert await resolve_collection(indexer, "m", 8) == ("collection", "m", 8)
    bump.assert_awaited_once_with(_REASON)
    assert indexer._needs_reindex is True


@pytest.mark.asyncio
async def test_no_recreate_does_not_bump():
    indexer = _Indexer(recreate=False)
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        await resolve_collection(indexer, "m", 8)
    bump.assert_not_awaited()
    assert indexer._needs_reindex is False


@pytest.mark.asyncio
async def test_a_failed_create_after_the_delete_still_bumps():
    indexer = _Indexer(recreate=True, fail=True)
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        with pytest.raises(RuntimeError):
            await resolve_collection(indexer, "m", 8)
    bump.assert_awaited_once_with(_REASON)
    assert indexer._needs_reindex is True


@pytest.mark.asyncio
async def test_a_pending_reindex_flag_is_preserved_without_a_new_bump():
    indexer = _Indexer(recreate=False, needs_reindex=True)
    with patch(_BUMP, new=AsyncMock(return_value=True)) as bump:
        await resolve_collection(indexer, "m", 8)
    bump.assert_not_awaited()
    assert indexer._needs_reindex is True
