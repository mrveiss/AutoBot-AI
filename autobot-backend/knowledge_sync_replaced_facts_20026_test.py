# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-indexing a changed file replaces its facts, and only once the new ones are stored (#20026)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge_sync_incremental import FileMetadata, IncrementalKnowledgeSync, SyncMetrics, _delete_fact_safe


class TestAChangedFileReplacesItsFacts20026:
    """A re-indexed file's old facts go once the new ones are stored, and never before."""

    def _sync(self, tmp_path):
        sync = IncrementalKnowledgeSync.__new__(IncrementalKnowledgeSync)
        sync.project_root = tmp_path
        sync.file_metadata = {}
        sync.kb = MagicMock()
        sync.kb.delete_fact = AsyncMock()
        return sync

    def _metadata(self, path, fact_ids):
        return FileMetadata(
            path=str(path), relative_path=path.name, content_hash="h", size=1, modified_time=1.0, fact_ids=fact_ids
        )

    def test_a_stored_result_returns_only_the_ids_it_replaced(self, tmp_path):
        doc = tmp_path / "doc.md"
        sync = self._sync(tmp_path)
        sync.file_metadata[str(doc)] = self._metadata(doc, ["old", "kept"])
        replaced = sync._update_metadata_from_results([doc], [self._metadata(doc, ["kept", "new"])], SyncMetrics())
        assert replaced == ["old"]
        assert sync.file_metadata[str(doc)].fact_ids == ["kept", "new"]

    @pytest.mark.parametrize("result", [None, RuntimeError("store failed")])
    def test_a_failed_store_keeps_the_old_facts_tracked(self, tmp_path, result):
        doc = tmp_path / "doc.md"
        sync = self._sync(tmp_path)
        sync.file_metadata[str(doc)] = self._metadata(doc, ["old"])
        assert sync._update_metadata_from_results([doc], [result], SyncMetrics()) == []
        assert sync.file_metadata[str(doc)].fact_ids == ["old"]

    def test_a_new_file_replaces_nothing(self, tmp_path):
        doc = tmp_path / "doc.md"
        sync = self._sync(tmp_path)
        assert sync._update_metadata_from_results([doc], [self._metadata(doc, ["new"])], SyncMetrics()) == []

    @pytest.mark.asyncio
    async def test_a_sync_pass_deletes_the_replaced_facts(self, tmp_path):
        doc = tmp_path / "doc.md"
        sync = self._sync(tmp_path)
        sync.max_concurrent_files = 1
        sync.auto_invalidation_enabled = False
        sync.file_metadata[str(doc)] = self._metadata(doc, ["old"])
        sync._process_file_with_gpu_chunking = AsyncMock(return_value=self._metadata(doc, ["new"]))
        calls = MagicMock()
        sync._save_sync_state = AsyncMock(side_effect=lambda: calls.saved())
        sync.kb.delete_fact = AsyncMock(side_effect=lambda fid: calls.deleted(fid))
        await sync._process_sync_changes([doc], [], SyncMetrics())
        assert [c[0] for c in calls.mock_calls] == ["saved", "deleted"], "state is saved before anything is deleted"
        sync.kb.delete_fact.assert_awaited_once_with("old")

    @pytest.mark.asyncio
    async def test_a_delete_the_kb_reports_as_failed_is_not_counted_as_done(self):
        kb = MagicMock()
        kb.delete_fact = AsyncMock(return_value={"status": "error", "message": "boom"})
        assert await _delete_fact_safe(kb, "old") is False
        kb.delete_fact = AsyncMock(return_value={"status": "success"})
        assert await _delete_fact_safe(kb, "old") is True
