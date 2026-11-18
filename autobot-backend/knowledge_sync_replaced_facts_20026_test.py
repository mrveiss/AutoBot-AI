# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-indexing a changed file replaces its facts, and only once the new ones are stored (#20026)."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

import knowledge_sync_incremental as sync_module
import knowledge_sync_replacement as replacement
from knowledge_sync_incremental import FileMetadata, IncrementalKnowledgeSync, SyncMetrics


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
    async def test_a_sync_pass_saves_state_before_deleting(self, tmp_path, monkeypatch):
        doc = tmp_path / "doc.md"
        sync = self._sync(tmp_path)
        sync.max_concurrent_files = 1
        sync.auto_invalidation_enabled = False
        sync.file_metadata[str(doc)] = self._metadata(doc, ["old"])
        sync._process_file_with_gpu_chunking = AsyncMock(return_value=self._metadata(doc, ["new"]))
        calls = MagicMock()
        sync._save_sync_state = AsyncMock(side_effect=lambda: calls.saved())
        monkeypatch.setattr(
            sync_module, "delete_replaced_facts", AsyncMock(side_effect=lambda kb, ids: calls.deleted(ids))
        )
        await sync._process_sync_changes([doc], [], SyncMetrics())
        assert calls.mock_calls[0][0] == "saved" and calls.mock_calls[1] == call.deleted(["old"])


class TestOnlyTheSyncsOwnUntouchedFactsGo:
    """Maintainer decision on #20028: own facts, unmodified, audited first."""

    @pytest.fixture(autouse=True)
    def _audit(self, monkeypatch):
        self.audit = AsyncMock(return_value=True)
        monkeypatch.setattr(replacement, "_audit_deletion", self.audit)
        monkeypatch.setattr(replacement, "_is_protected", lambda metadata: bool(metadata.get("pinned")))
        monkeypatch.setattr(replacement, "_provenance_defaults", lambda: {"verification_status": "unverified"})

    def _kb(self, metadata, delete=None):
        kb = MagicMock()
        kb.get_fact = MagicMock(return_value={"metadata": metadata})
        kb.redis_client.hget = MagicMock(return_value=None)
        kb.delete_fact = AsyncMock(return_value=delete or {"status": "success"})
        return kb

    @pytest.mark.asyncio
    async def test_an_untouched_sync_fact_is_audited_then_deleted(self):
        kb = self._kb({"ingest_route": "incremental_sync"})
        assert await replacement.delete_replaced_facts(kb, ["f"]) == 1
        self.audit.assert_awaited_once()
        kb.delete_fact.assert_awaited_once_with("f")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "metadata",
        [
            {"ingest_route": "incremental_sync", "updated_at": "2026-10-30T00:00:00+00:00"},
            {"ingest_route": "incremental_sync", "pinned": True},
            {"ingest_route": "incremental_sync", "tags": ["mine"]},  # add_tags_to_fact, rename, bulk tag
            {"ingest_route": "incremental_sync", "tags": []},  # a tag removed leaves the key behind
            {"ingest_route": "incremental_sync", "shared_by": "u1", "shared_at": "2026-10-30"},  # share_fact
            {"ingest_route": "incremental_sync", "verification_status": "verified"},  # a default changed
            {"ingest_route": "incremental_sync", "a_field_no_writer_has_yet": 1},  # any future writer
            {"ingest_route": "connector"},
            {},
        ],
    )
    async def test_an_edited_protected_or_foreign_fact_stays(self, metadata):
        kb = self._kb(metadata)
        assert await replacement.delete_replaced_facts(kb, ["f"]) == 0
        self.audit.assert_not_awaited()
        kb.delete_fact.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_assigned_category_keeps_the_fact(self):
        kb = self._kb({"ingest_route": "incremental_sync"})
        kb.redis_client.hget = MagicMock(return_value="cat-1")
        assert await replacement.delete_replaced_facts(kb, ["f"]) == 0
        kb.delete_fact.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_audit_keeps_the_fact(self):
        self.audit.return_value = False
        kb = self._kb({"ingest_route": "incremental_sync"})
        assert await replacement.delete_replaced_facts(kb, ["f"]) == 0
        kb.delete_fact.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_delete_the_kb_reports_as_failed_is_not_counted(self):
        kb = self._kb({"ingest_route": "incremental_sync"}, delete={"status": "error", "message": "boom"})
        assert await replacement.delete_replaced_facts(kb, ["f"]) == 0

    @pytest.mark.asyncio
    async def test_a_missing_fact_is_nothing_to_do_and_one_failure_stops_nothing(self):
        kb = self._kb({"ingest_route": "incremental_sync"})
        kb.get_fact = MagicMock(
            side_effect=[None, RuntimeError("redis"), {"metadata": {"ingest_route": "incremental_sync"}}]
        )
        assert await replacement.delete_replaced_facts(kb, ["a", "b", "c"]) == 1


@pytest.mark.asyncio
async def test_the_removal_paths_delete_reports_a_kb_failure():
    kb = MagicMock()
    kb.delete_fact = AsyncMock(return_value={"status": "error", "message": "boom"})
    assert await sync_module._delete_fact_safe(kb, "old") is False
    kb.delete_fact = AsyncMock(return_value={"status": "success"})
    assert await sync_module._delete_fact_safe(kb, "old") is True


def test_a_real_sync_fact_passes_the_real_predicate():
    """Unstubbed: what the store really writes for a sync chunk must qualify, or nothing is ever deleted."""
    from knowledge.facts import _apply_provenance_defaults, _fact_is_protected

    metadata = {key: "x" for key in replacement._SYNC_FACT_KEYS}
    metadata["ingest_route"] = replacement.SYNC_INGEST_ROUTE
    _apply_provenance_defaults(metadata)
    assert not _fact_is_protected(metadata)
    assert replacement.is_replaceable(metadata)
    assert not replacement.is_replaceable({**metadata, "tags": ["mine"]})
    assert not replacement.is_replaceable({**metadata, "pinned": True})


@pytest.mark.asyncio
async def test_a_refused_audit_row_keeps_the_fact(monkeypatch):
    """Unstubbed down to the store: the row's write failing is what keeps the fact."""
    from services.audit import audit as canonical

    monkeypatch.setattr(canonical.store, "insert_event", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(canonical, "_project", AsyncMock())
    assert await replacement._audit_deletion("f", {"relative_path": "docs/a.md"}) is False
    monkeypatch.setattr(canonical.store, "insert_event", AsyncMock())
    assert await replacement._audit_deletion("f", {"relative_path": "docs/a.md"}) is True
