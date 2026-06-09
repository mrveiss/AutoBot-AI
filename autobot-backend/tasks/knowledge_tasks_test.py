# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for knowledge-base cleanup Celery tasks (Issue #4455).

Covers:
- cleanup_orphan_documents: dry-run, orphan detection, batch deletion.
- cleanup_generated_files: TTL filtering, dry-run, bytes_freed accounting.
- _crontab_from_string: malformed cron fallback.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py stubs celery when it isn't installed in the dev venv.
from tasks.knowledge_tasks import (
    _CLEANUP_EXCLUDE_PATTERNS,
    _cleanup_files_older_than,
    _cleanup_orphan_documents_async,
    _collect_orphan_doc_ids,
    _is_excluded,
    _run_async_in_loop,
)

# ---------------------------------------------------------------------------
# _collect_orphan_doc_ids
# ---------------------------------------------------------------------------


def _fake_collection(ids: list[str], metadatas: list[dict]) -> MagicMock:
    """Build a MagicMock ChromaDB collection whose get_all_paginated returns data."""
    coll = MagicMock()
    coll.get.return_value = {"ids": ids, "metadatas": metadatas}
    return coll


def test_collect_orphan_doc_ids_identifies_missing_paths(tmp_path):
    existing = tmp_path / "present.md"
    existing.write_text("hello", encoding="utf-8")
    missing = tmp_path / "gone.md"  # never created

    ids = ["doc-present", "doc-missing"]
    metadatas = [
        {"file_path": str(existing)},
        {"file_path": str(missing)},
    ]
    coll = _fake_collection(ids, metadatas)

    orphan_ids, orphan_paths, scanned = _collect_orphan_doc_ids(coll)

    assert scanned == 2
    assert orphan_ids == ["doc-missing"]
    assert orphan_paths == [str(missing)]


def test_collect_orphan_doc_ids_handles_legacy_path_key(tmp_path):
    missing = tmp_path / "legacy-gone.md"
    ids = ["legacy-doc"]
    metadatas = [{"path": str(missing)}]  # legacy key, not file_path
    coll = _fake_collection(ids, metadatas)

    orphan_ids, orphan_paths, scanned = _collect_orphan_doc_ids(coll)

    assert scanned == 1
    assert orphan_ids == ["legacy-doc"]
    assert orphan_paths == [str(missing)]


def test_collect_orphan_doc_ids_skips_entries_without_path():
    ids = ["no-meta", "empty-meta"]
    metadatas = [None, {}]
    coll = _fake_collection(ids, metadatas)

    orphan_ids, orphan_paths, scanned = _collect_orphan_doc_ids(coll)

    assert scanned == 2
    assert orphan_ids == []
    assert orphan_paths == []


# ---------------------------------------------------------------------------
# _cleanup_orphan_documents_async
# ---------------------------------------------------------------------------


def _make_service_with_collection(collection: MagicMock) -> MagicMock:
    """Return a MagicMock DocIndexerService exposing an initialised collection."""
    svc = MagicMock()
    svc._initialized = True
    svc._collection = collection
    return svc


def test_cleanup_orphan_documents_async_dry_run_does_not_delete(tmp_path):
    missing = tmp_path / "missing.md"
    ids = ["orphan-1"]
    metadatas = [{"file_path": str(missing)}]
    coll = _fake_collection(ids, metadatas)
    svc = _make_service_with_collection(coll)

    with patch(
        "services.knowledge.doc_indexer.get_doc_indexer_service",
        return_value=svc,
    ):
        result = _run_async_in_loop(_cleanup_orphan_documents_async(dry_run=True))

    assert result["status"] == "success"
    assert result["dry_run"] is True
    assert result["scanned"] == 1
    assert result["removed"] == 0
    assert result["sample_removed_paths"] == [str(missing)]
    coll.delete.assert_not_called()


def test_cleanup_orphan_documents_async_deletes_orphans(tmp_path):
    kept = tmp_path / "kept.md"
    kept.write_text("ok", encoding="utf-8")
    gone = tmp_path / "gone.md"

    ids = ["keeper", "orphan"]
    metadatas = [{"file_path": str(kept)}, {"file_path": str(gone)}]
    coll = _fake_collection(ids, metadatas)
    svc = _make_service_with_collection(coll)

    with patch(
        "services.knowledge.doc_indexer.get_doc_indexer_service",
        return_value=svc,
    ):
        result = _run_async_in_loop(_cleanup_orphan_documents_async(dry_run=False))

    assert result["status"] == "success"
    assert result["dry_run"] is False
    assert result["scanned"] == 2
    assert result["removed"] == 1
    coll.delete.assert_called_once_with(ids=["orphan"])


def test_cleanup_orphan_documents_async_skipped_when_collection_none():
    svc = MagicMock()
    svc._initialized = True
    svc._collection = None

    with patch(
        "services.knowledge.doc_indexer.get_doc_indexer_service",
        return_value=svc,
    ):
        result = _run_async_in_loop(_cleanup_orphan_documents_async(dry_run=False))

    assert result["status"] == "skipped"
    assert result["reason"] == "collection_unavailable"


# ---------------------------------------------------------------------------
# _cleanup_files_older_than
# ---------------------------------------------------------------------------


def _touch(path: Path, content: str, age_seconds: float) -> None:
    """Create a file and backdate its mtime by age_seconds."""
    path.write_text(content, encoding="utf-8")
    past = time.time() - age_seconds
    import os as _os

    _os.utime(path, (past, past))


def test_cleanup_files_older_than_filters_by_mtime(tmp_path):
    old_file = tmp_path / "old.bin"
    new_file = tmp_path / "new.bin"
    _touch(old_file, "old" * 100, age_seconds=10 * 86400)  # 10 days old
    _touch(new_file, "new" * 100, age_seconds=1 * 3600)  # 1 hour old

    cutoff = time.time() - (7 * 86400)  # 7-day TTL
    scanned, removed, bytes_freed = _cleanup_files_older_than([tmp_path], cutoff, dry_run=False)

    assert scanned == 2
    assert removed == 1
    assert bytes_freed > 0
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_files_older_than_dry_run_preserves_files(tmp_path):
    old_file = tmp_path / "old.bin"
    _touch(old_file, "old" * 100, age_seconds=10 * 86400)

    cutoff = time.time() - (7 * 86400)
    scanned, removed, bytes_freed = _cleanup_files_older_than([tmp_path], cutoff, dry_run=True)

    assert scanned == 1
    assert removed == 0
    assert bytes_freed == 0
    assert old_file.exists()


def test_cleanup_files_older_than_skips_missing_directory(tmp_path):
    missing = tmp_path / "does-not-exist"
    scanned, removed, bytes_freed = _cleanup_files_older_than([missing], time.time(), dry_run=False)
    assert (scanned, removed, bytes_freed) == (0, 0, 0)


def test_cleanup_files_older_than_recurses_subdirectories(tmp_path):
    subdir = tmp_path / "nested"
    subdir.mkdir()
    old_file = subdir / "deep-old.bin"
    _touch(old_file, "x" * 50, age_seconds=30 * 86400)

    cutoff = time.time() - (7 * 86400)
    scanned, removed, _ = _cleanup_files_older_than([tmp_path], cutoff, dry_run=False)

    assert scanned == 1
    assert removed == 1
    assert not old_file.exists()


# ---------------------------------------------------------------------------
# Issue #5083: exclude patterns guard persistent artefacts from cleanup.
# ---------------------------------------------------------------------------


def test_cleanup_excludes_sqlite_files(tmp_path):
    """Stale sqlite/journal/WAL files must be preserved regardless of age."""
    stale_log = tmp_path / "old.log"
    stale_sqlite = tmp_path / "chroma.sqlite"
    stale_journal = tmp_path / "chroma.sqlite-journal"
    stale_wal = tmp_path / "database.wal"
    stale_aof = tmp_path / "appendonly.aof"
    stale_rdb = tmp_path / "dump.rdb"
    for f in (stale_log, stale_sqlite, stale_journal, stale_wal, stale_aof, stale_rdb):
        _touch(f, "payload" * 20, age_seconds=30 * 86400)

    cutoff = time.time() - (7 * 86400)
    scanned, removed, _ = _cleanup_files_older_than([tmp_path], cutoff, dry_run=False)

    # All 6 files scanned; only .log removed.
    assert scanned == 6
    assert removed == 1
    assert not stale_log.exists()
    assert stale_sqlite.exists()
    assert stale_journal.exists()
    assert stale_wal.exists()
    assert stale_aof.exists()
    assert stale_rdb.exists()


def test_cleanup_excludes_files_under_chromadb_parent_dir(tmp_path):
    """Files inside a chromadb/ directory are preserved even if they have
    an otherwise-deletable name (regression guard for parent-dir matching)."""
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()
    protected = chroma_dir / "segment.bin"
    _touch(protected, "payload", age_seconds=30 * 86400)

    other_dir = tmp_path / "embeddings_cache"
    other_dir.mkdir()
    stale = other_dir / "old.pkl"
    _touch(stale, "stale", age_seconds=30 * 86400)

    cutoff = time.time() - (7 * 86400)
    scanned, removed, _ = _cleanup_files_older_than([tmp_path], cutoff, dry_run=False)

    assert scanned == 2
    assert removed == 1
    assert protected.exists()
    assert not stale.exists()


def test_cleanup_excludes_files_under_redis_parent_dir(tmp_path):
    """Files under a redis-data/ directory are preserved."""
    redis_dir = tmp_path / "redis-data"
    redis_dir.mkdir()
    protected = redis_dir / "dump.bin"
    _touch(protected, "payload", age_seconds=30 * 86400)

    cutoff = time.time() - (7 * 86400)
    scanned, removed, _ = _cleanup_files_older_than([tmp_path], cutoff, dry_run=False)

    assert scanned == 1
    assert removed == 0
    assert protected.exists()


def test_is_excluded_matches_filename_patterns(tmp_path):
    assert _is_excluded(tmp_path / "foo.sqlite")
    assert _is_excluded(tmp_path / "foo.sqlite3")
    assert _is_excluded(tmp_path / "foo.sqlite-journal")
    assert _is_excluded(tmp_path / "foo.sqlite-wal")
    assert _is_excluded(tmp_path / "foo.sqlite-shm")
    assert _is_excluded(tmp_path / "db.wal")
    assert _is_excluded(tmp_path / "appendonly.aof")
    assert _is_excluded(tmp_path / "dump.rdb")
    assert _is_excluded(tmp_path / "my-chroma-file.bin")
    assert _is_excluded(tmp_path / "redis-dump.bin")


def test_is_excluded_matches_parent_dir_patterns(tmp_path):
    nested = tmp_path / "chromadb" / "nested" / "file.bin"
    assert _is_excluded(nested)
    nested_redis = tmp_path / "redis-data" / "file.bin"
    assert _is_excluded(nested_redis)


def test_is_excluded_allows_unrelated_files(tmp_path):
    assert not _is_excluded(tmp_path / "cache" / "embedding.pkl")
    assert not _is_excluded(tmp_path / "exports" / "report.json")
    assert not _is_excluded(tmp_path / "chunks_temp" / "chunk-42.bin")


def test_cleanup_exclude_patterns_is_tuple():
    # Immutable constant guard — prevents accidental runtime mutation.
    assert isinstance(_CLEANUP_EXCLUDE_PATTERNS, tuple)
    assert len(_CLEANUP_EXCLUDE_PATTERNS) > 0


# ---------------------------------------------------------------------------
# _crontab_from_string
# ---------------------------------------------------------------------------


def _have_real_celery() -> bool:
    try:
        import celery

        # Real celery's Celery class lives in celery.app module, not a stub shim.
        return celery.Celery.__module__.startswith("celery")
    except Exception:
        return False


@pytest.mark.skipif(
    not _have_real_celery(),
    reason="requires real celery package (test stub cannot parse cron expressions)",
)
def test_crontab_from_string_accepts_valid_expression():
    from celery_app import _crontab_from_string

    cron = _crontab_from_string("30 4 * * *")
    # crontab stores minute/hour as sets of ints
    assert 30 in cron.minute
    assert 4 in cron.hour


@pytest.mark.skipif(
    not _have_real_celery(),
    reason="requires real celery package",
)
def test_crontab_from_string_falls_back_on_malformed():
    from celery_app import _crontab_from_string

    cron = _crontab_from_string("not a cron")
    assert 0 in cron.minute
    assert 3 in cron.hour
