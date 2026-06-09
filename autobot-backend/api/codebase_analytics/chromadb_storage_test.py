# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for chromadb_storage._delete_source_documents (Issue #6695).

Background: the helper passed AsyncChromaDBCollection.get/.delete (both
``async def``) to ``asyncio.to_thread``, which calls but does not await them.
The result was a coroutine object, not a dict — ``existing.get("ids")`` then
raised AttributeError silently swallowed by the broad except. Source
documents were never deleted; re-indexing accumulated duplicates.

These tests fail against the pre-#6695 code (``existing`` is a coroutine →
``existing.get("ids")`` raises ``AttributeError: 'coroutine' object has no
attribute 'get'`` and the bug branch logs a warning instead of deleting).
"""

from unittest.mock import AsyncMock

import pytest

from api.codebase_analytics.chromadb_storage import _delete_source_documents


class TestDeleteSourceDocuments:
    """Issue #6695: async-in-to_thread bug for AsyncChromaDBCollection."""

    @pytest.mark.asyncio
    async def test_awaits_get_directly_and_deletes_returned_ids(self):
        """``collection.get`` and ``.delete`` must be awaited (not to_thread'd)."""
        collection = AsyncMock()
        collection.get = AsyncMock(return_value={"ids": ["a", "b", "c"]})
        collection.delete = AsyncMock(return_value=None)

        await _delete_source_documents(collection, "task-1", "source-X")

        collection.get.assert_awaited_once_with(where={"source_id": "source-X"}, include=[])
        collection.delete.assert_awaited_once_with(ids=["a", "b", "c"])

    @pytest.mark.asyncio
    async def test_no_op_when_no_existing_documents(self):
        """Empty result must not call delete."""
        collection = AsyncMock()
        collection.get = AsyncMock(return_value={"ids": []})
        collection.delete = AsyncMock(return_value=None)

        await _delete_source_documents(collection, "task-2", "source-Y")

        collection.get.assert_awaited_once()
        collection.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_batches_delete_for_large_id_sets(self):
        """``delete`` must be called once per 5000-id batch."""
        ids = [f"id-{i}" for i in range(12_345)]  # 3 batches: 5000 + 5000 + 2345
        collection = AsyncMock()
        collection.get = AsyncMock(return_value={"ids": ids})
        collection.delete = AsyncMock(return_value=None)

        await _delete_source_documents(collection, "task-3", "source-Z")

        assert collection.delete.await_count == 3
        called_batches = [c.kwargs["ids"] for c in collection.delete.await_args_list]
        assert len(called_batches[0]) == 5000
        assert len(called_batches[1]) == 5000
        assert len(called_batches[2]) == 2345

    @pytest.mark.asyncio
    async def test_swallows_exceptions_with_warning(self, caplog):
        """Errors must not propagate but must be logged."""
        import logging

        collection = AsyncMock()
        collection.get = AsyncMock(side_effect=RuntimeError("chroma down"))

        with caplog.at_level(logging.WARNING):
            await _delete_source_documents(collection, "task-4", "source-W")

        assert any("Could not delete source" in r.message for r in caplog.records)
