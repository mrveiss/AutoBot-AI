#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for incremental KB sync - Issue #3281

Acceptance criteria verified:
  - Only changed/new files are re-indexed on each sync
  - Deleted files are removed from the index
  - Sync time for unchanged vaults is under 2 seconds
  - Full rebuild still available via force_full flag
"""

import hashlib
import sys
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies that are not installed in the dev venv.
# These are only needed at runtime on the target VM; tests use mocks.
# ---------------------------------------------------------------------------
_STUBS = [
    "llama_index",
    "llama_index.core",
    "llama_index.core.indices",
    "llama_index.core.storage",
    "llama_index.core.storage.storage_context",
    "llama_index.vector_stores",
    "llama_index.vector_stores.redis",
    "aiofiles",
    "redis",
    "redis.asyncio",
    "chromadb",
    "sentence_transformers",
    "transformers",
]
for _mod in _STUBS:
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

from knowledge_sync_incremental import (
    FileMetadata,
    IncrementalKnowledgeSync,
    SyncMetrics,
    _classify_file_change,
    _delete_fact_safe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_metadata(path: str, content_hash: str, mtime: float) -> FileMetadata:
    return FileMetadata(
        path=path,
        relative_path=path,
        content_hash=content_hash,
        size=100,
        modified_time=mtime,
        fact_ids=["fact-1", "fact-2"],
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Tests: _classify_file_change
# ---------------------------------------------------------------------------


class TestClassifyFileChange:
    """Unit tests for the pure helper that classifies file changes."""

    def test_new_file_returns_new(self):
        metadata: Dict[str, Any] = {}
        stat = MagicMock(st_mtime=1000.0)
        result = _classify_file_change(metadata, "/new/file.md", _sha256("content"), stat, Path("file.md"))
        assert result == "new"

    def test_unchanged_file_returns_none(self):
        h = _sha256("same content")
        metadata = {"/path/file.md": _make_file_metadata("/path/file.md", h, 1000.0)}
        stat = MagicMock(st_mtime=1000.0)
        result = _classify_file_change(metadata, "/path/file.md", h, stat, Path("file.md"))
        assert result is None

    def test_changed_content_returns_changed(self):
        old_hash = _sha256("old content")
        metadata = {"/path/file.md": _make_file_metadata("/path/file.md", old_hash, 1000.0)}
        stat = MagicMock(st_mtime=1000.0)
        result = _classify_file_change(
            metadata,
            "/path/file.md",
            _sha256("new content"),
            stat,
            Path("file.md"),
        )
        assert result == "changed"

    def test_timestamp_only_change_returns_timestamp(self):
        h = _sha256("same content")
        metadata = {"/path/file.md": _make_file_metadata("/path/file.md", h, 1000.0)}
        stat = MagicMock(st_mtime=2000.0)  # mtime differs but hash is same
        result = _classify_file_change(metadata, "/path/file.md", h, stat, Path("file.md"))
        assert result == "timestamp"


# ---------------------------------------------------------------------------
# Tests: SyncMetrics
# ---------------------------------------------------------------------------


class TestSyncMetrics:
    def test_record_file_analysis(self):
        m = SyncMetrics()
        m.record_file_analysis(total_scanned=10, changed_count=5, new_count=2, removed_count=1)
        assert m.total_files_scanned == 10
        assert m.files_changed == 3  # changed_count - new_count
        assert m.files_added == 2
        assert m.files_removed == 1

    def test_calculate_performance(self):
        m = SyncMetrics(total_chunks_processed=100, total_processing_time=2.0)
        m.calculate_performance()
        assert m.avg_chunks_per_second == pytest.approx(50.0)

    def test_get_change_analysis_log(self):
        m = SyncMetrics(
            total_files_scanned=5,
            files_changed=2,
            files_added=1,
            files_removed=0,
        )
        log = m.get_change_analysis_log()
        assert "5" in log
        assert "2" in log


# ---------------------------------------------------------------------------
# Tests: _delete_fact_safe
# ---------------------------------------------------------------------------


class TestDeleteFactSafe:
    @pytest.mark.asyncio
    async def test_successful_delete_returns_true(self):
        kb = MagicMock()
        kb.delete_fact = AsyncMock(return_value=None)
        result = await _delete_fact_safe(kb, "fact-123")
        assert result is True
        kb.delete_fact.assert_awaited_once_with("fact-123")

    @pytest.mark.asyncio
    async def test_failed_delete_returns_false(self):
        kb = MagicMock()
        kb.delete_fact = AsyncMock(side_effect=RuntimeError("KB unavailable"))
        result = await _delete_fact_safe(kb, "fact-456")
        assert result is False


# ---------------------------------------------------------------------------
# Tests: IncrementalKnowledgeSync - only changed files are processed
# ---------------------------------------------------------------------------


class TestIncrementalKnowledgeSyncChangedFiles:
    """Verify acceptance criterion: only changed/new files are re-indexed."""

    def _make_sync(self, tmp_path: Path) -> IncrementalKnowledgeSync:
        sync = IncrementalKnowledgeSync.__new__(IncrementalKnowledgeSync)
        sync.project_root = tmp_path
        sync.sync_state_path = tmp_path / "data" / "incremental_sync_state.json"
        sync.file_metadata_path = tmp_path / "data" / "file_metadata.json"
        sync.kb = None
        sync.semantic_chunker = None
        sync.file_metadata = {}
        sync.current_sync_time = time.time()
        sync.max_concurrent_files = 4
        sync.chunk_batch_size = 50
        sync.enable_background_sync = True
        sync.knowledge_ttl_hours = 24 * 7
        sync.auto_invalidation_enabled = False  # disable TTL invalidation in unit tests
        sync.doc_patterns = ["*.md"]
        return sync

    @pytest.mark.asyncio
    async def test_unchanged_file_skipped(self, tmp_path):
        """File whose hash matches stored metadata must not be re-processed."""
        sync = self._make_sync(tmp_path)
        doc = tmp_path / "doc.md"
        doc.write_text("stable content", encoding="utf-8")

        h = _sha256("stable content")
        stat = doc.stat()
        sync.file_metadata[str(doc)] = _make_file_metadata(str(doc), h, stat.st_mtime)

        changed, removed, new = await sync._analyze_file_changes([doc])
        assert doc not in changed
        assert doc not in new
        assert str(doc) not in removed

    @pytest.mark.asyncio
    async def test_changed_file_included(self, tmp_path):
        """File whose content changed must appear in changed list."""
        sync = self._make_sync(tmp_path)
        doc = tmp_path / "doc.md"
        doc.write_text("new content", encoding="utf-8")

        old_hash = _sha256("old content")
        sync.file_metadata[str(doc)] = _make_file_metadata(str(doc), old_hash, 0.0)

        changed, removed, new = await sync._analyze_file_changes([doc])
        assert doc in changed

    @pytest.mark.asyncio
    async def test_new_file_included(self, tmp_path):
        """File not in metadata must appear in new list."""
        sync = self._make_sync(tmp_path)
        doc = tmp_path / "new_doc.md"
        doc.write_text("brand new", encoding="utf-8")

        changed, removed, new = await sync._analyze_file_changes([doc])
        assert doc in new
        assert doc in changed  # new files are also in combined list

    @pytest.mark.asyncio
    async def test_deleted_file_detected_as_removed(self, tmp_path):
        """File tracked in metadata but absent from disk must appear in removed."""
        sync = self._make_sync(tmp_path)
        missing = str(tmp_path / "gone.md")
        sync.file_metadata[missing] = _make_file_metadata(missing, _sha256("x"), 0.0)

        # Pass empty file list — file is gone
        changed, removed, new = await sync._analyze_file_changes([])
        assert missing in removed

    @pytest.mark.asyncio
    async def test_removed_obsolete_knowledge_deletes_facts(self, tmp_path):
        """Removed files must have their KB facts deleted."""
        sync = self._make_sync(tmp_path)
        kb = MagicMock()
        kb.delete_fact = AsyncMock(return_value=None)
        sync.kb = kb

        gone = str(tmp_path / "gone.md")
        sync.file_metadata[gone] = _make_file_metadata(gone, _sha256("old"), 0.0)

        await sync._remove_obsolete_knowledge([gone])

        assert gone not in sync.file_metadata
        assert kb.delete_fact.await_count == 2  # two fact_ids in fixture

    @pytest.mark.asyncio
    async def test_unchanged_vault_completes_quickly(self, tmp_path):
        """Acceptance: sync time for unchanged vault must be under 2 seconds."""
        sync = self._make_sync(tmp_path)
        # Pre-populate metadata so nothing changes
        for i in range(20):
            doc = tmp_path / f"doc{i}.md"
            doc.write_text(f"content {i}", encoding="utf-8")
            h = _sha256(f"content {i}")
            stat = doc.stat()
            sync.file_metadata[str(doc)] = _make_file_metadata(str(doc), h, stat.st_mtime)

        start = time.monotonic()
        changed, removed, new = await sync._analyze_file_changes([tmp_path / f"doc{i}.md" for i in range(20)])
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"Unchanged vault analysis took {elapsed:.3f}s (limit 2s)"
        assert len(changed) == 0
        assert len(removed) == 0


# ---------------------------------------------------------------------------
# Tests: force_full flag clears metadata for full rebuild
# ---------------------------------------------------------------------------


class TestForceFullRebuild:
    """Acceptance: full rebuild available via force_full."""

    @pytest.mark.asyncio
    async def test_force_full_clears_metadata(self):
        """manual_sync(force_full=True) must clear file_metadata to force re-index."""
        from services.knowledge_sync_service import KnowledgeSyncService

        service = KnowledgeSyncService()
        service.incremental_sync = MagicMock()
        service.incremental_sync.file_metadata = {"existing_file": MagicMock()}
        service.incremental_sync.perform_incremental_sync = AsyncMock(return_value=SyncMetrics())

        await service.manual_sync(force_full=True)

        assert service.incremental_sync.file_metadata == {}

    @pytest.mark.asyncio
    async def test_incremental_sync_preserves_metadata(self):
        """manual_sync(force_full=False) must NOT clear file_metadata."""
        from services.knowledge_sync_service import KnowledgeSyncService

        service = KnowledgeSyncService()
        service.incremental_sync = MagicMock()
        original_metadata = {"existing_file": MagicMock()}
        service.incremental_sync.file_metadata = original_metadata
        service.incremental_sync.perform_incremental_sync = AsyncMock(return_value=SyncMetrics())

        await service.manual_sync(force_full=False)

        assert service.incremental_sync.file_metadata is original_metadata
