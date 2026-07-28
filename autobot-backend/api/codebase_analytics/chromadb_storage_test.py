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

import json
from unittest.mock import AsyncMock

import pytest

from api.codebase_analytics.chromadb_storage import (
    _delete_source_documents,
    _prepare_batch_data,
    _prepare_import_document,
    _prepare_imports_batch,
)


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


class TestPrepareImportDocument:
    """Issue #12364: per-file import lists are persisted to the index so
    import-tree/dependencies can read from ChromaDB instead of re-walking
    the filesystem on every request."""

    def test_metadata_round_trips_import_list(self):
        doc_id, doc_text, metadata = _prepare_import_document(
            "pkg/mod.py", ["os", "pkg.other"], idx=0, source_id="src-A"
        )

        assert metadata["type"] == "import"
        assert metadata["file_path"] == "pkg/mod.py"
        assert json.loads(metadata["imports"]) == ["os", "pkg.other"]
        assert metadata["source_id"] == "src-A"
        assert doc_id == "src-A_import_0_pkg/mod.py"
        assert "pkg/mod.py" in doc_text

    def test_no_source_id_omits_source_metadata_and_prefix(self):
        doc_id, _doc_text, metadata = _prepare_import_document("mod.py", [], idx=3, source_id=None)

        assert "source_id" not in metadata
        assert doc_id == "import_3_mod.py"


class TestPrepareImportsBatch:
    """#12364: only .py files get import documents; count reflects offset."""

    async def test_only_python_files_get_import_documents(self):
        files = {
            "a.py": {"imports": ["os"]},
            "b.js": {"imports": []},
            "sub/c.py": {"imports": ["a"]},
        }
        batch_ids, batch_documents, batch_metadatas = [], [], []

        async def _noop_progress(**kwargs):
            return None

        total = await _prepare_imports_batch(
            files, batch_ids, batch_documents, batch_metadatas, _noop_progress, total_items=10, items_offset=5
        )

        stored_paths = {m["file_path"] for m in batch_metadatas}
        assert stored_paths == {"a.py", "sub/c.py"}
        assert total == 5 + 2

    async def test_prepare_batch_data_includes_import_documents(self):
        """End-to-end: _prepare_batch_data (the real call site) emits import
        docs alongside functions/classes/stats."""
        analysis_results = {
            "all_functions": [],
            "all_classes": [],
            "files": {"mod.py": {"imports": ["os", "sys"]}},
            "stats": {
                "total_files": 1,
                "total_lines": 10,
                "python_files": 1,
                "javascript_files": 0,
                "vue_files": 0,
                "total_functions": 0,
                "total_classes": 0,
                "last_indexed": "now",
                "lines_by_category": {},
            },
        }

        async def _noop_progress(**kwargs):
            return None

        def _noop_phase(*args, **kwargs):
            return None

        batch_ids, batch_documents, batch_metadatas = await _prepare_batch_data(
            analysis_results, "task-import", _noop_progress, _noop_phase, source_id="src-A"
        )

        import_metas = [m for m in batch_metadatas if m["type"] == "import"]
        assert len(import_metas) == 1
        assert import_metas[0]["file_path"] == "mod.py"
        assert json.loads(import_metas[0]["imports"]) == ["os", "sys"]
        assert batch_ids and batch_documents
