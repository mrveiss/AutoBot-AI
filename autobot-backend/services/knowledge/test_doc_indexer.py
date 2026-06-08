# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive tests for DocIndexerService — Issue #4383.

Covers:
- index_all(force=False) with empty collection (should force full index — #4350 fix)
- index_all(force=True) (re-indexes all files, updates cache)
- index_all(force=False) with non-empty collection (incremental mode)
- Hash cache update after indexing
- _filter_changed_files() with various cache states
- needs_indexing() condition
- Edge cases: empty files, missing files, corrupted hash cache
"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing doc_indexer
# ---------------------------------------------------------------------------

_STUBS: dict = {}


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__package__ = name
    _STUBS[name] = mod
    sys.modules.setdefault(name, mod)
    return mod


# autobot_shared.ssot_config — only get_ollama_url is used at module level
_ssot = _make_stub("autobot_shared.ssot_config")
_ssot.get_ollama_url = lambda: "http://localhost:11434"  # type: ignore[attr-defined]

# constants.path_constants — PATH.DATA_DIR and PATH.PROJECT_ROOT must be real Paths
_constants = _make_stub("constants")
_path_constants = _make_stub("constants.path_constants")


class _FakePATH:
    DATA_DIR = Path("/tmp/test_autobot_data")  # nosec B108 - test/controlled code uses tmpdir intentionally
    PROJECT_ROOT = Path("/tmp/test_autobot_root")  # nosec B108 - test/controlled code uses tmpdir intentionally


_path_constants.PATH = _FakePATH()  # type: ignore[attr-defined]

# Load doc_indexer bypassing the services package __init__ (which needs the
# full stack).  Using spec_from_file_location keeps the module name canonical
# so patch() paths work correctly.
_BACKEND_ROOT = Path(__file__).parent.parent.parent  # autobot-backend/
_DOC_INDEXER_PATH = Path(__file__).parent / "doc_indexer.py"
_spec = importlib.util.spec_from_file_location("services.knowledge.doc_indexer", str(_DOC_INDEXER_PATH))
assert _spec and _spec.loader, "Could not load doc_indexer spec"
_doc_indexer_mod = importlib.util.module_from_spec(_spec)
sys.modules["services.knowledge.doc_indexer"] = _doc_indexer_mod
_spec.loader.exec_module(_doc_indexer_mod)  # type: ignore[union-attr]

# Ensure the package stub exposes doc_indexer as an attribute so patch()
# can resolve "services.knowledge.doc_indexer.<name>" correctly.
if "services.knowledge" in sys.modules:
    sys.modules["services.knowledge"].doc_indexer = _doc_indexer_mod  # type: ignore[attr-defined]

from services.knowledge.doc_indexer import (  # noqa: E402 — after sys.modules patch
    DocIndexerService,
    _compute_file_hash,
    _filter_changed_files,
    _load_hash_cache,
    _normalize_path,
    _save_hash_cache,
    _should_exclude,
    get_doc_indexer_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE = "services.knowledge.doc_indexer"


def _make_service(
    initialized: bool = True,
    collection_count: int = 0,
    root_dir: Path = Path("/tmp/test_autobot_root"),  # nosec B108 - test/controlled code uses tmpdir intentionally
) -> DocIndexerService:
    """Build a DocIndexerService with pre-wired mocks."""
    svc = DocIndexerService.__new__(DocIndexerService)
    svc._initialized = initialized
    svc._root_dir = root_dir
    svc._embed_model = MagicMock()
    svc._embed_model.get_text_embedding = MagicMock(return_value=[0.1] * 128)

    mock_collection = MagicMock()
    mock_collection.count = MagicMock(return_value=collection_count)
    mock_collection.upsert = MagicMock()
    svc._collection = mock_collection

    mock_client = MagicMock()
    svc._client = mock_client
    return svc


# ---------------------------------------------------------------------------
# Unit tests: pure functions
# ---------------------------------------------------------------------------


class TestFilterChangedFiles:
    """Tests for _filter_changed_files()."""

    def test_all_new_files_returned_when_cache_empty(self, tmp_path) -> None:
        """Empty cache → every file is treated as changed."""
        f1 = tmp_path / "a.md"
        f1.write_text("hello", encoding="utf-8")
        f2 = tmp_path / "b.md"
        f2.write_text("world", encoding="utf-8")

        files = [(str(f1), 1), (str(f2), 2)]
        changed, new_hashes = _filter_changed_files(files, {}, tmp_path)

        assert len(changed) == 2
        assert len(new_hashes) == 2
        assert "a.md" in new_hashes
        assert "b.md" in new_hashes

    def test_unchanged_file_excluded_from_result(self, tmp_path) -> None:
        """File whose hash matches cache entry is excluded from changed list."""
        f = tmp_path / "unchanged.md"
        f.write_text("same content", encoding="utf-8")
        current_hash = _compute_file_hash(str(f))

        changed, new_hashes = _filter_changed_files([(str(f), 1)], {"unchanged.md": current_hash}, tmp_path)

        assert len(changed) == 0
        assert new_hashes.get("unchanged.md") == current_hash

    def test_changed_file_included_in_result(self, tmp_path) -> None:
        """File with stale cache hash is included in changed list."""
        f = tmp_path / "changed.md"
        f.write_text("new content", encoding="utf-8")

        changed, new_hashes = _filter_changed_files([(str(f), 1)], {"changed.md": "stale_hash_abc123"}, tmp_path)

        assert len(changed) == 1
        assert changed[0][0] == str(f)

    def test_mixed_changed_and_unchanged(self, tmp_path) -> None:
        """Only changed files appear in result; all hashes stored."""
        f_old = tmp_path / "old.md"
        f_old.write_text("old", encoding="utf-8")
        old_hash = _compute_file_hash(str(f_old))

        f_new = tmp_path / "new.md"
        f_new.write_text("new content here", encoding="utf-8")

        files = [(str(f_old), 1), (str(f_new), 2)]
        cache = {"old.md": old_hash, "new.md": "wrong_hash"}
        changed, new_hashes = _filter_changed_files(files, cache, tmp_path)

        assert len(changed) == 1
        assert changed[0][0] == str(f_new)
        assert len(new_hashes) == 2

    def test_hashes_use_relative_paths_as_keys(self, tmp_path) -> None:
        """new_hashes keys must be relative to root_dir, not absolute."""
        sub = tmp_path / "docs"
        sub.mkdir()
        f = sub / "guide.md"
        f.write_text("content", encoding="utf-8")

        _, new_hashes = _filter_changed_files([(str(f), 2)], {}, tmp_path)

        assert "docs/guide.md" in new_hashes


class TestHashCache:
    """Tests for _load_hash_cache() and _save_hash_cache()."""

    def test_save_and_load_roundtrip(self, tmp_path) -> None:
        """Save then load returns identical dict."""
        hashes = {"file1.md": "abc", "file2.md": "def"}

        with patch(f"{_MODULE}.HASH_CACHE_FILE", tmp_path / ".doc_index_hashes.json"):
            _save_hash_cache(hashes)
            loaded = _load_hash_cache()

        assert loaded == hashes

    def test_load_returns_empty_when_file_missing(self, tmp_path) -> None:
        """Missing cache file returns empty dict."""
        with patch(f"{_MODULE}.HASH_CACHE_FILE", tmp_path / "nonexistent.json"):
            result = _load_hash_cache()
        assert result == {}

    def test_load_returns_empty_on_corrupt_json(self, tmp_path) -> None:
        """Corrupt JSON in cache file returns empty dict without raising."""
        bad_file = tmp_path / ".doc_index_hashes.json"
        bad_file.write_text("not valid json {{{{", encoding="utf-8")

        with patch(f"{_MODULE}.HASH_CACHE_FILE", bad_file):
            result = _load_hash_cache()

        assert result == {}

    def test_save_creates_parent_dirs(self, tmp_path) -> None:
        """_save_hash_cache creates missing parent directories."""
        nested = tmp_path / "a" / "b" / "c" / "hashes.json"
        with patch(f"{_MODULE}.HASH_CACHE_FILE", nested):
            _save_hash_cache({"k": "v"})
        assert nested.exists()


class TestShouldExclude:
    """Tests for _should_exclude()."""

    def test_excludes_backup_file(self) -> None:
        assert _should_exclude("/docs/guide_backup.md")

    def test_excludes_tmp_file(self) -> None:
        assert _should_exclude("/docs/guide.tmp")

    def test_excludes_archives_path(self) -> None:
        assert _should_exclude("/docs/archives/old.md")

    def test_does_not_exclude_normal_md(self) -> None:
        assert not _should_exclude("/docs/features/authentication.md")

    def test_excludes_log_file(self) -> None:
        assert _should_exclude("/logs/debug.log")


# ---------------------------------------------------------------------------
# Unit tests: DocIndexerService
# ---------------------------------------------------------------------------


class TestNeedsIndexing:
    """Tests for DocIndexerService.needs_indexing()."""

    def test_returns_true_when_not_initialized(self) -> None:
        svc = _make_service(initialized=False, collection_count=0)
        svc._collection = None
        assert svc.needs_indexing() is True

    def test_returns_true_when_collection_empty(self) -> None:
        svc = _make_service(initialized=True, collection_count=0)
        assert svc.needs_indexing() is True

    def test_returns_false_when_collection_has_docs(self) -> None:
        svc = _make_service(initialized=True, collection_count=42)
        assert svc.needs_indexing() is False


class TestIndexAll:
    """Tests for DocIndexerService.index_all()."""

    # ------------------------------------------------------------------
    # Helper: fake filesystem of markdown files
    # ------------------------------------------------------------------

    def _make_md_files(self, root: Path) -> None:
        """Create a minimal set of discoverable markdown files."""
        docs = root / "docs" / "features"
        docs.mkdir(parents=True)
        (docs / "feature_a.md").write_text("# Feature A\n\nContent here.\n", encoding="utf-8")
        (docs / "feature_b.md").write_text("# Feature B\n\nOther content.\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Test: empty collection forces full index (#4350 fix)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_collection_forces_full_index(self, tmp_path) -> None:
        """index_all(force=False) with empty collection bypasses hash cache (#4350)."""
        self._make_md_files(tmp_path)
        svc = _make_service(initialized=True, collection_count=0, root_dir=tmp_path)

        # Put a stale cache that would skip all files in incremental mode
        stale_cache = {"docs/features/feature_a.md": "stale", "docs/features/feature_b.md": "stale"}
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(stale_cache), encoding="utf-8")

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files") as mock_discover,
            patch.object(svc, "_index_single_file_content", new=AsyncMock()) as mock_index,
        ):
            # Return two fake files from TIER_3_DIRS-like path
            f_a = str(tmp_path / "docs" / "features" / "feature_a.md")
            f_b = str(tmp_path / "docs" / "features" / "feature_b.md")
            mock_discover.return_value = [(f_a, 2), (f_b, 2)]

            await svc.index_all(force=False)

        # Both files must be indexed — cache was ignored because collection was empty
        assert mock_index.call_count == 2, (
            f"Expected 2 files indexed (full index forced by empty collection), " f"got {mock_index.call_count}"
        )

    @pytest.mark.asyncio
    async def test_force_true_reindexes_all_files(self, tmp_path) -> None:
        """index_all(force=True) re-indexes all files ignoring cache state."""
        self._make_md_files(tmp_path)
        svc = _make_service(initialized=True, collection_count=100, root_dir=tmp_path)

        # Pre-populate cache with matching hashes (incremental would skip these)
        f_a = tmp_path / "docs" / "features" / "feature_a.md"
        f_b = tmp_path / "docs" / "features" / "feature_b.md"
        current_hashes = {
            "docs/features/feature_a.md": _compute_file_hash(str(f_a)),
            "docs/features/feature_b.md": _compute_file_hash(str(f_b)),
        }
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(current_hashes), encoding="utf-8")

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files") as mock_discover,
            patch.object(svc, "_index_single_file_content", new=AsyncMock()) as mock_index,
        ):
            mock_discover.return_value = [(str(f_a), 2), (str(f_b), 2)]
            await svc.index_all(force=True)

        # force=True must index all even when hashes match
        assert mock_index.call_count == 2

    @pytest.mark.asyncio
    async def test_incremental_mode_skips_unchanged_files(self, tmp_path) -> None:
        """index_all(force=False) skips files with matching hash cache."""
        self._make_md_files(tmp_path)
        svc = _make_service(initialized=True, collection_count=50, root_dir=tmp_path)

        f_a = tmp_path / "docs" / "features" / "feature_a.md"
        f_b = tmp_path / "docs" / "features" / "feature_b.md"
        current_hashes = {
            "docs/features/feature_a.md": _compute_file_hash(str(f_a)),
            "docs/features/feature_b.md": _compute_file_hash(str(f_b)),
        }
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(current_hashes), encoding="utf-8")

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files") as mock_discover,
            patch.object(svc, "_index_single_file_content", new=AsyncMock()) as mock_index,
        ):
            mock_discover.return_value = [(str(f_a), 2), (str(f_b), 2)]
            result = await svc.index_all(force=False)

        # All files unchanged — nothing should be indexed
        assert mock_index.call_count == 0
        assert result.skipped == 2

    @pytest.mark.asyncio
    async def test_incremental_mode_indexes_only_changed_files(self, tmp_path) -> None:
        """index_all(force=False) indexes only files with stale/missing hashes."""
        self._make_md_files(tmp_path)
        svc = _make_service(initialized=True, collection_count=50, root_dir=tmp_path)

        f_a = tmp_path / "docs" / "features" / "feature_a.md"
        f_b = tmp_path / "docs" / "features" / "feature_b.md"

        # feature_a has matching hash; feature_b has stale hash
        cache = {
            "docs/features/feature_a.md": _compute_file_hash(str(f_a)),
            "docs/features/feature_b.md": "stale_hash",
        }
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(cache), encoding="utf-8")

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files") as mock_discover,
            patch.object(svc, "_index_single_file_content", new=AsyncMock()) as mock_index,
        ):
            mock_discover.return_value = [(str(f_a), 2), (str(f_b), 2)]
            await svc.index_all(force=False)

        # Only feature_b should be indexed
        assert mock_index.call_count == 1
        indexed_path = mock_index.call_args[0][0]
        assert "feature_b" in indexed_path

    @pytest.mark.asyncio
    async def test_hash_cache_updated_after_force_index(self, tmp_path) -> None:
        """After force=True index_all, hash cache must be updated for all files."""
        self._make_md_files(tmp_path)
        svc = _make_service(initialized=True, collection_count=0, root_dir=tmp_path)

        f_a = tmp_path / "docs" / "features" / "feature_a.md"
        f_b = tmp_path / "docs" / "features" / "feature_b.md"
        cache_file = tmp_path / ".doc_index_hashes.json"

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files") as mock_discover,
            patch.object(svc, "_index_single_file_content", new=AsyncMock()),
        ):
            mock_discover.return_value = [(str(f_a), 2), (str(f_b), 2)]
            await svc.index_all(force=True)

        # Cache file must exist and contain both file entries
        assert cache_file.exists()
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        assert "docs/features/feature_a.md" in saved
        assert "docs/features/feature_b.md" in saved

    @pytest.mark.asyncio
    async def test_returns_error_result_on_init_failure(self, tmp_path) -> None:
        """index_all returns error IndexResult when initialization fails."""
        svc = _make_service(initialized=False, root_dir=tmp_path)
        svc._collection = None

        with patch.object(svc, "initialize", new=AsyncMock(return_value=False)):
            result = await svc.index_all()

        assert result.errors
        assert "Failed to initialize" in result.errors[0]

    @pytest.mark.asyncio
    async def test_no_files_discovered_returns_empty_result(self, tmp_path) -> None:
        """index_all returns empty result when no files are discovered."""
        svc = _make_service(initialized=True, collection_count=0, root_dir=tmp_path)

        with patch(f"{_MODULE}._discover_files", return_value=[]):
            result = await svc.index_all()

        assert result.total_files == 0
        assert result.success == 0

    @pytest.mark.asyncio
    async def test_elapsed_seconds_populated(self, tmp_path) -> None:
        """index_all always populates elapsed_seconds."""
        self._make_md_files(tmp_path)
        svc = _make_service(initialized=True, collection_count=100, root_dir=tmp_path)

        f_a = tmp_path / "docs" / "features" / "feature_a.md"
        cache = {"docs/features/feature_a.md": _compute_file_hash(str(f_a))}
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(cache), encoding="utf-8")

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files", return_value=[(str(f_a), 1)]),
            patch.object(svc, "_index_single_file_content", new=AsyncMock()),
        ):
            result = await svc.index_all(force=False)

        assert result.elapsed_seconds >= 0


class TestIndexFile:
    """Tests for DocIndexerService.index_file()."""

    @pytest.mark.asyncio
    async def test_returns_failed_for_missing_file(self, tmp_path) -> None:
        """index_file returns failed result for nonexistent file."""
        svc = _make_service(initialized=True, collection_count=0, root_dir=tmp_path)
        result = await svc.index_file(tmp_path / "missing.md", tier=1, force=True)

        assert result.failed == 1
        assert result.success == 0

    @pytest.mark.asyncio
    async def test_skips_file_with_matching_hash(self, tmp_path) -> None:
        """index_file skips indexing when hash matches cache and force=False."""
        f = tmp_path / "guide.md"
        f.write_text("# Guide\n\nContent here.\n", encoding="utf-8")
        current_hash = _compute_file_hash(str(f))
        cache = {"guide.md": current_hash}
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(cache), encoding="utf-8")

        svc = _make_service(initialized=True, collection_count=10, root_dir=tmp_path)

        with patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file):
            result = await svc.index_file(f, tier=2, force=False)

        assert result.skipped == 1
        assert result.success == 0

    @pytest.mark.asyncio
    async def test_force_true_bypasses_hash_check(self, tmp_path) -> None:
        """index_file with force=True indexes even if hash matches cache."""
        f = tmp_path / "guide.md"
        f.write_text("# Guide\n\nSome section content here.\n\nMore text.\n", encoding="utf-8")
        current_hash = _compute_file_hash(str(f))
        cache = {"guide.md": current_hash}
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(cache), encoding="utf-8")

        svc = _make_service(initialized=True, collection_count=10, root_dir=tmp_path)

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch.object(svc, "_index_file_chunks", new=AsyncMock(return_value=(1, 1))),
        ):
            result = await svc.index_file(f, tier=2, force=True)

        assert result.skipped == 0
        assert result.success == 1

    @pytest.mark.asyncio
    async def test_empty_file_is_skipped(self, tmp_path) -> None:
        """index_file skips files that contain only whitespace."""
        f = tmp_path / "empty.md"
        f.write_text("   \n\n  ", encoding="utf-8")
        svc = _make_service(initialized=True, collection_count=10, root_dir=tmp_path)

        with patch(f"{_MODULE}.HASH_CACHE_FILE", tmp_path / ".hashes.json"):
            result = await svc.index_file(f, tier=3, force=True)

        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_successful_index_returns_success_one(self, tmp_path) -> None:
        """index_file returns success=1 when chunk is indexed."""
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n\n## Section A\n\nSome useful content here.\n", encoding="utf-8")
        svc = _make_service(initialized=True, collection_count=10, root_dir=tmp_path)

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", tmp_path / ".hashes.json"),
            patch.object(svc, "_index_file_chunks", new=AsyncMock(return_value=(1, 1))),
        ):
            result = await svc.index_file(f, tier=1, force=True)

        assert result.success == 1
        assert result.failed == 0


class TestIndexAllEmpty4350Fix:
    """Regression tests specifically for #4350: empty collection forces full index."""

    @pytest.mark.asyncio
    async def test_needs_indexing_true_overrides_cache_match(self, tmp_path) -> None:
        """#4350: needs_indexing() == True must override matching hash cache."""
        docs = tmp_path / "docs" / "features"
        docs.mkdir(parents=True)
        f = docs / "api.md"
        f.write_text("# API\n\n## Section\n\nApi content here.\n", encoding="utf-8")

        svc = _make_service(initialized=True, collection_count=0, root_dir=tmp_path)
        assert svc.needs_indexing() is True  # Empty collection

        # Cache says hash matches (would skip in pure incremental mode)
        current_hash = _compute_file_hash(str(f))
        cache = {"docs/features/api.md": current_hash}
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(cache), encoding="utf-8")

        indexed_files = []

        async def _track_index(file_path, tier, result) -> None:
            indexed_files.append(file_path)

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files", return_value=[(str(f), 2)]),
            patch.object(svc, "_index_single_file_content", side_effect=_track_index),
        ):
            await svc.index_all(force=False)

        assert len(indexed_files) == 1, "Empty collection must trigger full index even when hash cache matches (#4350)"

    @pytest.mark.asyncio
    async def test_non_empty_collection_uses_incremental(self, tmp_path) -> None:
        """#4350 fix does NOT apply when collection already has documents."""
        docs = tmp_path / "docs" / "features"
        docs.mkdir(parents=True)
        f = docs / "api.md"
        f.write_text("# API\n\nContent.\n", encoding="utf-8")

        svc = _make_service(initialized=True, collection_count=10, root_dir=tmp_path)
        assert svc.needs_indexing() is False  # Non-empty collection

        current_hash = _compute_file_hash(str(f))
        cache = {"docs/features/api.md": current_hash}
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text(json.dumps(cache), encoding="utf-8")

        indexed_files = []

        async def _track_index(file_path, tier, result) -> None:
            indexed_files.append(file_path)

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", cache_file),
            patch(f"{_MODULE}._discover_files", return_value=[(str(f), 2)]),
            patch.object(svc, "_index_single_file_content", side_effect=_track_index),
        ):
            await svc.index_all(force=False)

        # Non-empty + matching hash → nothing indexed (incremental skipped)
        assert len(indexed_files) == 0


class TestEdgeCases:
    """Edge case tests for hash cache and file handling."""

    def test_compute_file_hash_returns_empty_string_on_error(self, tmp_path) -> None:
        """_compute_file_hash returns '' for unreadable files (no exception raised)."""
        result = _compute_file_hash("/nonexistent/path/file.md")
        assert result == ""

    def test_compute_file_hash_consistent(self, tmp_path) -> None:
        """Same file content always produces same hash."""
        f = tmp_path / "test.md"
        f.write_text("consistent content", encoding="utf-8")
        h1 = _compute_file_hash(str(f))
        h2 = _compute_file_hash(str(f))
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_compute_file_hash_differs_for_different_content(self, tmp_path) -> None:
        """Different content produces different hashes."""
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("content A", encoding="utf-8")
        f2.write_text("content B", encoding="utf-8")
        assert _compute_file_hash(str(f1)) != _compute_file_hash(str(f2))

    @pytest.mark.asyncio
    async def test_index_all_with_corrupted_hash_cache(self, tmp_path) -> None:
        """Corrupted hash cache falls back gracefully to full index."""
        docs = tmp_path / "docs" / "features"
        docs.mkdir(parents=True)
        f = docs / "guide.md"
        f.write_text("# Guide\n\nContent.\n", encoding="utf-8")

        svc = _make_service(initialized=True, collection_count=0, root_dir=tmp_path)

        corrupt_cache = tmp_path / ".doc_index_hashes.json"
        corrupt_cache.write_text("{ invalid json !!!", encoding="utf-8")

        indexed_files = []

        async def _track(fp, tier, result) -> None:
            indexed_files.append(fp)

        with (
            patch(f"{_MODULE}.HASH_CACHE_FILE", corrupt_cache),
            patch(f"{_MODULE}._discover_files", return_value=[(str(f), 2)]),
            patch.object(svc, "_index_single_file_content", side_effect=_track),
        ):
            await svc.index_all(force=False)

        # With empty collection + corrupted cache, file must be indexed
        assert len(indexed_files) == 1

    def test_filter_changed_files_empty_file_list(self, tmp_path) -> None:
        """_filter_changed_files with empty file list returns empty results."""
        changed, hashes = _filter_changed_files([], {"some.md": "hash"}, tmp_path)
        assert changed == []
        assert hashes == {}


class TestHashCacheEdgeCases4382:
    """Edge case tests for hash cache — Issue #4382."""

    # ------------------------------------------------------------------
    # Symlinks
    # ------------------------------------------------------------------

    def test_compute_file_hash_follows_symlink(self, tmp_path) -> None:
        """_compute_file_hash hashes the target content, not the symlink path."""
        target = tmp_path / "real.md"
        target.write_text("real content", encoding="utf-8")
        link = tmp_path / "link.md"
        link.symlink_to(target)

        hash_via_target = _compute_file_hash(str(target))
        hash_via_link = _compute_file_hash(str(link))
        assert hash_via_target == hash_via_link

    def test_filter_changed_files_symlink_matches_target_hash(self, tmp_path) -> None:
        """Symlink and target produce the same cache key hash (#4382)."""
        target = tmp_path / "real.md"
        target.write_text("content", encoding="utf-8")
        link = tmp_path / "link.md"
        link.symlink_to(target)

        target_hash = _compute_file_hash(str(target))

        # Cache uses resolved key for target; symlink should resolve to same hash
        _, link_rel = _normalize_path(str(link), tmp_path)
        changed, new_hashes = _filter_changed_files([(str(link), 1)], {link_rel: target_hash}, tmp_path)
        # Hash matches → file should NOT appear as changed
        assert len(changed) == 0

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def test_compute_file_hash_returns_empty_on_permission_error(self, tmp_path) -> None:
        """_compute_file_hash returns '' on PermissionError without raising."""
        f = tmp_path / "secret.md"
        f.write_text("secret", encoding="utf-8")
        f.chmod(0o000)
        try:
            result = _compute_file_hash(str(f))
            # On Linux running as root, chmod 000 is bypassed — skip assertion.
            if result != "":
                import os as _os

                assert _os.getuid() == 0, "Non-root should get empty hash for unreadable file"
        finally:
            f.chmod(0o644)

    def test_filter_changed_files_preserves_cached_hash_on_permission_error(self, tmp_path) -> None:
        """Unreadable file preserves cached hash and is NOT marked changed (#4382)."""
        f = tmp_path / "locked.md"
        f.write_text("data", encoding="utf-8")
        existing_hash = _compute_file_hash(str(f))
        f.chmod(0o000)
        try:
            import os as _os

            if _os.getuid() == 0:
                # Root bypasses chmod — skip this test
                return
            cache = {"locked.md": existing_hash}
            changed, new_hashes = _filter_changed_files([(str(f), 1)], cache, tmp_path)
            # File unreadable → hash preserved, not marked changed
            assert len(changed) == 0
            assert new_hashes.get("locked.md") == existing_hash
        finally:
            f.chmod(0o644)

    # ------------------------------------------------------------------
    # Path normalization
    # ------------------------------------------------------------------

    def test_normalize_path_returns_relative_key(self, tmp_path) -> None:
        """_normalize_path returns a relative path key under root_dir."""
        sub = tmp_path / "docs" / "api"
        sub.mkdir(parents=True)
        f = sub / "ref.md"
        f.write_text("x", encoding="utf-8")

        _, rel = _normalize_path(str(f), tmp_path)
        assert rel == str(Path("docs") / "api" / "ref.md")

    def test_normalize_path_symlink_resolves_consistently(self, tmp_path) -> None:
        """Symlink and its target produce the same relative path after resolution."""
        real_dir = tmp_path / "real_docs"
        real_dir.mkdir()
        target = real_dir / "guide.md"
        target.write_text("guide", encoding="utf-8")

        link_dir = tmp_path / "linked_docs"
        link_dir.symlink_to(real_dir)
        link_file = link_dir / "guide.md"

        _, rel_target = _normalize_path(str(target), tmp_path)
        _, rel_link = _normalize_path(str(link_file), tmp_path)
        # Both point to same inode → same relative path
        assert rel_target == rel_link

    def test_filter_changed_files_normalized_keys_match_cache(self, tmp_path) -> None:
        """_filter_changed_files uses normalized keys so relocation-safe lookup works."""
        sub = tmp_path / "docs"
        sub.mkdir()
        f = sub / "x.md"
        f.write_text("hello", encoding="utf-8")
        current_hash = _compute_file_hash(str(f))

        _, rel = _normalize_path(str(f), tmp_path)
        changed, _ = _filter_changed_files([(str(f), 1)], {rel: current_hash}, tmp_path)
        assert len(changed) == 0

    # ------------------------------------------------------------------
    # Circular symlinks (#4433)
    # ------------------------------------------------------------------

    def test_compute_file_hash_returns_empty_on_circular_symlink(self, tmp_path) -> None:
        """_compute_file_hash returns '' for a circular symlink without raising (#4433)."""
        link_a = tmp_path / "a.md"
        link_b = tmp_path / "b.md"
        link_a.symlink_to(link_b)
        link_b.symlink_to(link_a)

        result = _compute_file_hash(str(link_a))
        assert result == "", "Circular symlink must return '' not raise OSError"

    def test_filter_changed_files_preserves_cached_hash_on_circular_symlink(self, tmp_path) -> None:
        """Circular symlink preserves cached hash and is NOT marked changed (#4433)."""
        link_a = tmp_path / "loop_a.md"
        link_b = tmp_path / "loop_b.md"
        link_a.symlink_to(link_b)
        link_b.symlink_to(link_a)

        cache = {"loop_a.md": "cafebabe"}
        changed, new_hashes = _filter_changed_files([(str(link_a), 1)], cache, tmp_path)
        # Circular symlink → hash is '' → cached hash preserved, not marked changed
        assert len(changed) == 0
        assert new_hashes.get("loop_a.md") == "cafebabe"


class TestIndexChunkOversized4665:
    """Tests for oversized-chunk detection and split-retry logic — Issue #4665."""

    def _make_chunk(self, content: str = "x" * 200) -> Dict[str, Any]:
        return {
            "content": content,
            "section": "Section",
            "subsection": None,
            "file_path": "docs/test.md",
            "doc_type": "documentation",
            "category": "general",
            "title": "Test Doc",
        }

    # ------------------------------------------------------------------
    # _is_oversized_error
    # ------------------------------------------------------------------

    def test_is_oversized_error_too_large(self) -> None:
        """'too large' in error message → oversized."""
        assert DocIndexerService._is_oversized_error(ValueError("input too large"))

    def test_is_oversized_error_token(self) -> None:
        """'token' in error message → oversized."""
        assert DocIndexerService._is_oversized_error(RuntimeError("token limit exceeded"))

    def test_is_oversized_error_sequence_length(self) -> None:
        """'sequence length' in error message → oversized."""
        assert DocIndexerService._is_oversized_error(Exception("sequence length 600 > 512"))

    def test_is_oversized_error_context_length(self) -> None:
        """'context length' in error message → oversized."""
        assert DocIndexerService._is_oversized_error(Exception("context length exceeded"))

    def test_is_oversized_error_exceeds(self) -> None:
        """'exceeds' in error message → oversized."""
        assert DocIndexerService._is_oversized_error(Exception("length exceeds maximum"))

    def test_is_oversized_error_truncat(self) -> None:
        """'truncat' in error message → oversized (truncated/truncation)."""
        assert DocIndexerService._is_oversized_error(Exception("input truncated"))

    def test_is_oversized_error_generic_error_not_oversized(self) -> None:
        """Generic network error → not oversized."""
        assert not DocIndexerService._is_oversized_error(ConnectionError("connection refused"))

    def test_is_oversized_error_key_error_not_oversized(self) -> None:
        """KeyError → not oversized."""
        assert not DocIndexerService._is_oversized_error(KeyError("missing_key"))

    # ------------------------------------------------------------------
    # _index_chunk: normal success path
    # ------------------------------------------------------------------

    def test_index_chunk_returns_true_on_success(self) -> None:
        """_index_chunk returns True when embed+upsert succeed."""
        svc = _make_service()
        chunk = self._make_chunk("Short content for embedding.")
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)
        assert ok is True
        svc._embed_model.get_text_embedding.assert_called_once()

    # ------------------------------------------------------------------
    # _index_chunk: non-oversized error → logged, returns False, no split
    # ------------------------------------------------------------------

    def test_index_chunk_returns_false_on_non_oversized_error(self) -> None:
        """Non-oversized error → returns False, no split attempted."""
        svc = _make_service()
        svc._embed_model.get_text_embedding.side_effect = ConnectionError("connection refused")
        chunk = self._make_chunk()
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)
        assert ok is False
        # upsert must NOT be called (error happened before it)
        svc._collection.upsert.assert_not_called()

    # ------------------------------------------------------------------
    # _index_chunk: oversized → split, both halves succeed
    # ------------------------------------------------------------------

    def test_index_chunk_splits_on_oversized_both_halves_succeed(self):
        """Oversized embed error → content split in half, both halves stored, returns True."""
        svc = _make_service()

        content = "A" * 400
        # First call (full chunk) raises oversized; subsequent calls succeed.
        call_count = [0]

        def _fake_embed(text):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("input too large for model context length")
            return [0.1] * 128

        svc._embed_model.get_text_embedding.side_effect = _fake_embed
        chunk = self._make_chunk(content)
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        assert ok is True
        # 1 failed call + 2 half calls = 3 total embed calls
        assert call_count[0] == 3
        # Two successful upserts (one per half)
        assert svc._collection.upsert.call_count == 2

    # ------------------------------------------------------------------
    # _index_chunk: oversized → split, one half fails (still non-silent)
    # ------------------------------------------------------------------

    def test_index_chunk_splits_on_oversized_one_half_still_oversized(self):
        """Oversized: first half OK, second half oversized → recursion splits second half further.

        With multi-level splitting (#4702), a still-oversized half is split
        recursively rather than dropped.  This test verifies that the second
        half is split into quarters (depth 1) which then succeed.
        """
        svc = _make_service()

        content = "B" * 400
        call_count = [0]

        def _fake_embed(text):
            call_count[0] += 1
            if call_count[0] == 1:
                # Full chunk too large
                raise ValueError("token limit exceeded")
            if call_count[0] == 3:
                # Second half at depth 0 also too large → recursion continues
                raise ValueError("token limit exceeded")
            return [0.2] * 128

        svc._embed_model.get_text_embedding.side_effect = _fake_embed
        chunk = self._make_chunk(content)
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        # Full success: first half (call 2) + two quarters of second half (calls 4+5)
        assert ok is True
        assert svc._collection.upsert.call_count == 3

    # ------------------------------------------------------------------
    # _index_chunk: oversized → split, BOTH halves fail → returns False
    # ------------------------------------------------------------------

    def test_index_chunk_splits_on_oversized_both_halves_fail(self) -> None:
        """Oversized: both halves fail → returns False (no silent drop — warning logged)."""
        svc = _make_service()

        svc._embed_model.get_text_embedding.side_effect = ValueError("token limit exceeded")
        chunk = self._make_chunk("C" * 400)
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        assert ok is False
        svc._collection.upsert.assert_not_called()

    # ------------------------------------------------------------------
    # Warning is logged (not silently dropped) — #4665 regression guard
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # _split_and_embed: empty-string guard (#4921)
    # ------------------------------------------------------------------

    def test_split_and_embed_returns_false_on_empty_string(self) -> None:
        """_split_and_embed returns False immediately for empty content (#4921)."""
        svc = _make_service()
        ok = svc._split_and_embed("", "chunk_id", {}, "docs/test.md")
        assert ok is False
        # No embed call should happen — guard fires before any I/O
        svc._embed_model.get_text_embedding.assert_not_called()

    def test_split_and_embed_empty_half_after_bisect_does_not_embed(self):
        """Bisect of whitespace-only content produces empty halves that are skipped (#4921).

        A string like '   ' strips to '' on both sides — both recursive calls
        must return False without calling the embedding model.
        """
        svc = _make_service()

        # Force the initial call to fail with an oversized error so bisect runs
        call_count = [0]

        def _fake_embed(text):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("input too large for model context length")
            return [0.1] * 128

        svc._embed_model.get_text_embedding.side_effect = _fake_embed
        # Content that strips to empty on both bisected halves
        ok = svc._split_and_embed("   ", "chunk_id", {}, "docs/test.md")
        assert ok is False
        # Only one embed attempt (the initial oversized call) — halves are empty, skipped
        assert call_count[0] == 1

    def test_index_chunk_logs_warning_on_oversized(self, caplog):
        """Oversized chunk must emit a WARNING with doc path and char count (#4665)."""
        import logging

        svc = _make_service()

        call_count = [0]

        def _fake_embed(text):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("input too large")
            return [0.3] * 128

        svc._embed_model.get_text_embedding.side_effect = _fake_embed

        with caplog.at_level(logging.WARNING, logger="services.knowledge.doc_indexer"):
            chunk = self._make_chunk("D" * 400)
            svc._index_chunk(chunk, 0, 1, "docs/oversized.md", [], 1)

        assert any(
            "oversized" in r.message.lower() or "oversized" in r.getMessage().lower() for r in caplog.records
        ), "Expected WARNING with 'oversized' in message"
        assert any(
            "docs/oversized.md" in r.getMessage() for r in caplog.records
        ), "WARNING must include the document path"


class TestIndexChunkMultiLevelSplit4702:
    """Tests for multi-level recursive oversized-chunk split — Issue #4702."""

    def _make_chunk(self, content: str) -> Dict[str, Any]:
        return {
            "content": content,
            "section": "Section",
            "subsection": None,
            "file_path": "docs/test.md",
            "doc_type": "documentation",
            "category": "general",
            "title": "Test Doc",
        }

    # ------------------------------------------------------------------
    # Two-level split: halves are still too large, quarters succeed
    # ------------------------------------------------------------------

    def test_two_level_split_all_quarters_succeed(self):
        """Chunk too large → halves too large → quarters succeed → returns True."""
        svc = _make_service()

        # Track calls to identify which content sizes fail
        call_count = [0]

        def _fake_embed(text):
            call_count[0] += 1
            # First 3 calls (original + 2 halves) raise oversized;
            # subsequent calls (4 quarters) succeed.
            if call_count[0] <= 3:
                raise ValueError("input too large for model context length")
            return [0.1] * 128

        svc._embed_model.get_text_embedding.side_effect = _fake_embed
        chunk = self._make_chunk("A" * 800)
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        assert ok is True
        # 3 failed + 4 successful = 7 total embed calls
        assert call_count[0] == 7
        assert svc._collection.upsert.call_count == 4

    # ------------------------------------------------------------------
    # Three-level split: only some leaf nodes succeed
    # ------------------------------------------------------------------

    def test_three_level_split_partial_success(self):
        """Three-level split where some deepest pieces succeed → True (partial)."""
        svc = _make_service()

        call_count = [0]

        def _fake_embed(text):
            call_count[0] += 1
            # Calls 1–7 (original + 2 halves + 4 quarters) raise oversized;
            # 8 of the 8 depth-3 pieces: first 4 succeed, last 4 fail.
            if call_count[0] <= 7:
                raise ValueError("token limit exceeded")
            if call_count[0] <= 11:
                return [0.1] * 128
            raise ValueError("token limit exceeded")

        svc._embed_model.get_text_embedding.side_effect = _fake_embed
        chunk = self._make_chunk("B" * 1600)
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        assert ok is True
        # At least one piece stored
        assert svc._collection.upsert.call_count >= 1

    # ------------------------------------------------------------------
    # max_depth=4 cap: beyond depth 4, chunk is dropped (returns False
    # only if no sibling succeeded)
    # ------------------------------------------------------------------

    def test_always_oversized_drops_at_max_depth(self) -> None:
        """If every embed call raises oversized, chunk is dropped at max_depth → False."""
        svc = _make_service()
        svc._embed_model.get_text_embedding.side_effect = ValueError("input too large for model context length")
        chunk = self._make_chunk("C" * 3200)
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        assert ok is False
        svc._collection.upsert.assert_not_called()

    # ------------------------------------------------------------------
    # Chunk IDs at each depth carry the _L/_R suffix chain
    # ------------------------------------------------------------------

    def test_split_chunk_ids_carry_depth_suffix(self):
        """Sub-chunk IDs at depth 1 must end with _L0 or _R0."""
        svc = _make_service()

        call_count = [0]
        upserted_ids = []

        def _fake_embed(text):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("too large")
            return [0.1] * 128

        def _fake_upsert(ids, embeddings, documents, metadatas) -> None:
            upserted_ids.extend(ids)

        svc._embed_model.get_text_embedding.side_effect = _fake_embed
        svc._collection.upsert.side_effect = _fake_upsert

        chunk = self._make_chunk("D" * 400)
        svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        # Both sub-IDs must end with the depth-0 suffix
        assert any(uid.endswith("_L0") for uid in upserted_ids), f"Expected _L0 suffix in {upserted_ids}"
        assert any(uid.endswith("_R0") for uid in upserted_ids), f"Expected _R0 suffix in {upserted_ids}"

    # ------------------------------------------------------------------
    # Non-oversized error at any depth stops recursion immediately
    # ------------------------------------------------------------------

    def test_non_oversized_error_at_depth_1_drops_that_branch(self):
        """Non-oversized error at depth 1 → that branch is dropped, no deeper recursion."""
        svc = _make_service()

        call_count = [0]

        def _fake_embed(text):
            call_count[0] += 1
            if call_count[0] == 1:
                # Original chunk: oversized
                raise ValueError("input too large")
            if call_count[0] == 2:
                # Left half: non-oversized error
                raise ConnectionError("network error")
            return [0.1] * 128

        svc._embed_model.get_text_embedding.side_effect = _fake_embed
        chunk = self._make_chunk("E" * 400)
        ok = svc._index_chunk(chunk, 0, 1, "docs/test.md", [], 2)

        # Right half succeeded → partial success
        assert ok is True
        assert svc._collection.upsert.call_count == 1


class TestGetDocIndexerService:
    """Tests for the singleton factory."""

    def test_returns_same_instance(self) -> None:
        """get_doc_indexer_service() returns the same object on multiple calls."""
        import services.knowledge.doc_indexer as mod

        # Reset singleton for test isolation
        original = mod._doc_indexer
        mod._doc_indexer = None
        try:
            a = get_doc_indexer_service()
            b = get_doc_indexer_service()
            assert a is b
        finally:
            mod._doc_indexer = original

    def test_returns_doc_indexer_service_instance(self) -> None:
        """Factory returns a DocIndexerService instance."""
        import services.knowledge.doc_indexer as mod

        original = mod._doc_indexer
        mod._doc_indexer = None
        try:
            svc = get_doc_indexer_service()
            assert isinstance(svc, DocIndexerService)
        finally:
            mod._doc_indexer = original

    def test_factory_resolves_llm_service_lazily(self) -> None:
        """Factory calls get_llm_service() when llm_service arg is omitted (#4655)."""
        import services.knowledge.doc_indexer as mod

        original = mod._doc_indexer
        mod._doc_indexer = None
        mock_llm = MagicMock()
        try:
            with patch.dict(
                "sys.modules",
                {"services.llm_service": MagicMock(get_llm_service=lambda: mock_llm)},
            ):
                svc = get_doc_indexer_service()
            assert svc._llm_service is mock_llm
        finally:
            mod._doc_indexer = original

    def test_factory_accepts_explicit_llm_service(self) -> None:
        """Explicit llm_service arg is forwarded to DocIndexerService (#4655)."""
        import services.knowledge.doc_indexer as mod

        original = mod._doc_indexer
        mod._doc_indexer = None
        mock_llm = MagicMock()
        try:
            svc = get_doc_indexer_service(llm_service=mock_llm)
            assert svc._llm_service is mock_llm
        finally:
            mod._doc_indexer = original


class TestRunKbSynthesis:
    """Tests for DocIndexerService._run_kb_synthesis → LLM call path (#4655)."""

    @pytest.mark.asyncio
    async def test_run_kb_synthesis_calls_synthesize_docs_with_llm_service(self) -> None:
        """_run_kb_synthesis passes self._llm_service to get_kb_synthesizer (#4655)."""
        mock_llm = MagicMock()
        svc = DocIndexerService.__new__(DocIndexerService)
        svc._llm_service = mock_llm
        svc.synthesis_schema = MagicMock()
        svc.synthesis_schema.collections = []

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize_docs = AsyncMock()

        with patch.dict(
            "sys.modules",
            {
                "services.knowledge.kb_synthesizer": MagicMock(
                    get_kb_synthesizer=MagicMock(return_value=mock_synthesizer)
                )
            },
        ):
            await svc._run_kb_synthesis(["/docs/readme.md"])

        mock_synthesizer.synthesize_docs.assert_awaited_once()
        called_paths = mock_synthesizer.synthesize_docs.call_args[0][0]
        assert called_paths == ["/docs/readme.md"]

    @pytest.mark.asyncio
    async def test_calls_synthesizer_with_correct_args(self) -> None:
        """_run_kb_synthesis passes indexed_paths and collection_config to synthesize_docs (#4658)."""
        from services.knowledge.synthesis_schema_loader import CollectionConfig

        col_cfg = CollectionConfig(name="docs", paths=["docs/"], synthesis_target="", prompt_template="")
        mock_llm = MagicMock()
        svc = DocIndexerService.__new__(DocIndexerService)
        svc._llm_service = mock_llm
        svc.synthesis_schema = MagicMock()
        svc.synthesis_schema.collections = [col_cfg]

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize_docs = AsyncMock()

        with patch.dict(
            "sys.modules",
            {
                "services.knowledge.kb_synthesizer": MagicMock(
                    get_kb_synthesizer=MagicMock(return_value=mock_synthesizer)
                )
            },
        ):
            await svc._run_kb_synthesis(["docs/README.md"])

        mock_synthesizer.synthesize_docs.assert_awaited_once_with(["docs/README.md"], collection_config=col_cfg)

    @pytest.mark.asyncio
    async def test_swallows_exception_silently(self) -> None:
        """_run_kb_synthesis catches and logs exceptions without propagating (#4658)."""
        mock_llm = MagicMock()
        svc = DocIndexerService.__new__(DocIndexerService)
        svc._llm_service = mock_llm
        svc.synthesis_schema = MagicMock()
        svc.synthesis_schema.collections = []

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize_docs = AsyncMock(side_effect=Exception("synthesis boom"))

        with patch.dict(
            "sys.modules",
            {
                "services.knowledge.kb_synthesizer": MagicMock(
                    get_kb_synthesizer=MagicMock(return_value=mock_synthesizer)
                )
            },
        ):
            result = await svc._run_kb_synthesis(["/docs/foo.md"])

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_none_config_when_no_match(self) -> None:
        """_run_kb_synthesis passes collection_config=None when no collection matches (#4658)."""
        from services.knowledge.synthesis_schema_loader import CollectionConfig

        col_cfg = CollectionConfig(name="api", paths=["api/"], synthesis_target="", prompt_template="")
        mock_llm = MagicMock()
        svc = DocIndexerService.__new__(DocIndexerService)
        svc._llm_service = mock_llm
        svc.synthesis_schema = MagicMock()
        svc.synthesis_schema.collections = [col_cfg]

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize_docs = AsyncMock()

        with patch.dict(
            "sys.modules",
            {
                "services.knowledge.kb_synthesizer": MagicMock(
                    get_kb_synthesizer=MagicMock(return_value=mock_synthesizer)
                )
            },
        ):
            await svc._run_kb_synthesis(["docs/README.md"])

        mock_synthesizer.synthesize_docs.assert_awaited_once_with(["docs/README.md"], collection_config=None)


class TestFindCollectionConfig:
    """Tests for DocIndexerService._find_collection_config (#4658)."""

    def _make_svc(self, collections):
        from services.knowledge.synthesis_schema_loader import SynthesisSchema

        svc = DocIndexerService.__new__(DocIndexerService)
        schema = MagicMock(spec=SynthesisSchema)
        schema.collections = collections
        svc.synthesis_schema = schema
        return svc

    def test_returns_matching_config_when_path_prefix_found(self) -> None:
        """Returns the collection whose path prefix is a substring of an indexed path (#4658)."""
        from services.knowledge.synthesis_schema_loader import CollectionConfig

        col_cfg = CollectionConfig(name="docs", paths=["docs/"], synthesis_target="", prompt_template="")
        svc = self._make_svc([col_cfg])
        result = svc._find_collection_config(["docs/README.md"])
        assert result is col_cfg

    def test_returns_none_when_no_path_matches(self) -> None:
        """Returns None when no collection path is a substring of indexed_paths (#4658)."""
        from services.knowledge.synthesis_schema_loader import CollectionConfig

        col_cfg = CollectionConfig(name="src", paths=["src/"], synthesis_target="", prompt_template="")
        svc = self._make_svc([col_cfg])
        result = svc._find_collection_config(["tests/foo.py"])
        assert result is None

    def test_returns_none_on_empty_schema(self) -> None:
        """Returns None when synthesis_schema has no collections (#4658)."""
        svc = self._make_svc([])
        result = svc._find_collection_config(["docs/README.md"])
        assert result is None

    def test_returns_first_match_when_multiple_collections(self) -> None:
        """Returns the first matching collection when multiple collections match (#4658)."""
        from services.knowledge.synthesis_schema_loader import CollectionConfig

        col1 = CollectionConfig(name="docs", paths=["docs/"], synthesis_target="", prompt_template="")
        col2 = CollectionConfig(name="api", paths=["api/"], synthesis_target="", prompt_template="")
        svc = self._make_svc([col1, col2])
        result = svc._find_collection_config(["docs/guide.md", "api/ref.md"])
        assert result is col1


# ---------------------------------------------------------------------------
# Tests: DocIndexerService.search() — Issue #4953
# ---------------------------------------------------------------------------


class TestDocIndexerSearch:
    """search() exposes autobot_docs ChromaDB collection for RAGService merging."""

    @pytest.mark.asyncio
    async def test_search_not_initialized_returns_empty(self) -> None:
        """Returns [] when service is not initialised."""
        svc = _make_service(initialized=False, collection_count=0)
        result = await svc.search("what is autobot")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_empty_collection_returns_empty(self) -> None:
        """Returns [] when collection has no documents."""
        svc = _make_service(initialized=True, collection_count=0)
        result = await svc.search("what is autobot")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_returns_search_results(self) -> None:
        """Happy path: wraps ChromaDB hits into SearchResult objects."""
        svc = _make_service(initialized=True, collection_count=3)
        svc._collection.query = MagicMock(
            return_value={
                "documents": [["AutoBot is an AI platform.", "CLI usage guide."]],
                "metadatas": [
                    [
                        {"file_path": "docs/overview.md", "chunk_index": 0},
                        {"file_path": "docs/cli.md", "chunk_index": 1},
                    ]
                ],
                "distances": [[0.1, 0.3]],
            }
        )

        stub_mod = MagicMock()
        stub_mod.SearchResult = MagicMock(side_effect=lambda **kw: kw)

        with patch.dict("sys.modules", {"advanced_rag_optimizer": stub_mod}):
            results = await svc.search("what is autobot", n_results=2)

        assert len(results) == 2
        first = results[0]
        assert first["content"] == "AutoBot is an AI platform."
        assert first["semantic_score"] == pytest.approx(0.9)
        assert first["source_path"] == "docs/overview.md"
        assert first["metadata"]["source"] == "autobot_docs"

    @pytest.mark.asyncio
    async def test_search_caps_n_results_to_collection_count(self) -> None:
        """n_results is capped to avoid ChromaDB 'n_results > count' error."""
        svc = _make_service(initialized=True, collection_count=2)
        svc._collection.query = MagicMock(
            return_value={
                "documents": [["doc1", "doc2"]],
                "metadatas": [[{"file_path": "a.md"}, {"file_path": "b.md"}]],
                "distances": [[0.2, 0.4]],
            }
        )

        stub_mod = MagicMock()
        stub_mod.SearchResult = MagicMock(side_effect=lambda **kw: kw)
        with patch.dict("sys.modules", {"advanced_rag_optimizer": stub_mod}):
            await svc.search("query", n_results=100)

        call_kwargs = svc._collection.query.call_args[1]
        assert call_kwargs["n_results"] == 2  # capped to collection count

    @pytest.mark.asyncio
    async def test_search_exception_returns_empty(self) -> None:
        """query() failure returns [] instead of raising."""
        svc = _make_service(initialized=True, collection_count=5)
        svc._collection.query = MagicMock(side_effect=RuntimeError("chromadb unavailable"))

        stub_mod = MagicMock()
        stub_mod.SearchResult = MagicMock(side_effect=lambda **kw: kw)
        with patch.dict("sys.modules", {"advanced_rag_optimizer": stub_mod}):
            result = await svc.search("query")

        assert result == []
