# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the import-tree indexed-store convergence (Issue #12364).

Codebase Analytics ran on two non-shared data mechanisms: a pre-indexed
ChromaDB store (stats/declarations) and a live per-request filesystem walk
(import-tree/call-graph/duplicates/dependencies). These tests assert the
convergence for the import-tree panel: the indexed store is read first, the
live walk is used ONLY as a fallback when the index has no data for the
requested source, and the fallback also triggers a background index job so
the panel self-heals onto the fast path.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from api.codebase_analytics.endpoints import import_tree


def _write_module(directory, filename: str, body: str) -> None:
    (directory / filename).write_text(body, encoding="utf-8")


class TestLoadImportTreeFromIndex:
    """Unit tests for the primary (indexed-store) data path."""

    async def test_returns_none_when_no_collection(self):
        with patch.object(import_tree, "get_code_collection", return_value=None):
            result = await import_tree._load_import_tree_from_index("src-A")
        assert result is None

    async def test_returns_none_when_index_has_no_import_docs(self):
        with (
            patch.object(import_tree, "get_code_collection", return_value=MagicMock()),
            patch.object(import_tree, "get_all_paginated", return_value={"metadatas": []}),
        ):
            result = await import_tree._load_import_tree_from_index("src-A")
        assert result is None

    async def test_builds_bidirectional_tree_from_metadata(self):
        metadatas = [
            {"file_path": "app.py", "imports": json.dumps(["utils"])},
            {"file_path": "utils.py", "imports": json.dumps([])},
        ]
        with (
            patch.object(import_tree, "get_code_collection", return_value=MagicMock()),
            patch.object(import_tree, "get_all_paginated", return_value={"metadatas": metadatas}),
        ):
            result = await import_tree._load_import_tree_from_index("src-A")

        assert result is not None
        file_imports, file_imported_by = result
        assert file_imports["app.py"][0]["module"] == "utils"
        assert file_imports["app.py"][0]["file"] == "utils.py"
        assert file_imported_by["utils.py"][0]["file"] == "app.py"

    async def test_where_filter_scopes_to_source_id(self):
        captured = {}

        def _fake_get_all_paginated(collection, where=None, include=None):
            captured["where"] = where
            return {"metadatas": []}

        with (
            patch.object(import_tree, "get_code_collection", return_value=MagicMock()),
            patch.object(import_tree, "get_all_paginated", side_effect=_fake_get_all_paginated),
        ):
            await import_tree._load_import_tree_from_index("src-A")

        assert captured["where"] == {"$and": [{"type": "import"}, {"source_id": "src-A"}]}


class TestCrossSourceIsolation:
    """#12330: source A's indexed imports must never leak into source B's tree."""

    async def test_two_sources_never_bleed(self):
        all_metadatas = [
            {"file_path": "a_mod.py", "imports": json.dumps([]), "source_id": "A"},
            {"file_path": "b_mod.py", "imports": json.dumps([]), "source_id": "B"},
        ]

        def _fake_get_all_paginated(collection, where=None, include=None):
            wanted = where["$and"][1]["source_id"]
            return {"metadatas": [m for m in all_metadatas if m["source_id"] == wanted]}

        with (
            patch.object(import_tree, "get_code_collection", return_value=MagicMock()),
            patch.object(import_tree, "get_all_paginated", side_effect=_fake_get_all_paginated),
        ):
            result_a = await import_tree._load_import_tree_from_index("A")
            result_b = await import_tree._load_import_tree_from_index("B")

        assert "a_mod.py" in result_a[0]
        assert "b_mod.py" not in result_a[0]
        assert "b_mod.py" in result_b[0]
        assert "a_mod.py" not in result_b[0]


class TestGetImportTreeConvergence:
    """End-to-end: the endpoint prefers the index and falls back correctly."""

    async def test_uses_indexed_data_when_available(self):
        indexed = ({"app.py": []}, {})
        with (
            patch.object(import_tree, "_load_import_tree_from_index", AsyncMock(return_value=indexed)),
            patch.object(import_tree, "trigger_auto_index_if_unindexed", AsyncMock()) as auto_trigger,
            patch.object(import_tree, "_scan_import_tree_live", AsyncMock()) as live_scan,
        ):
            response = await import_tree.get_import_tree(source_id="src-A")

        body = json.loads(response.body)
        assert body["storage_type"] == "chromadb"
        live_scan.assert_not_called()
        auto_trigger.assert_not_called()

    async def test_falls_back_to_live_walk_and_triggers_auto_index_when_unindexed(self):
        with (
            patch.object(import_tree, "_load_import_tree_from_index", AsyncMock(return_value=None)),
            patch.object(import_tree, "trigger_auto_index_if_unindexed", AsyncMock()) as auto_trigger,
            patch.object(import_tree, "_scan_import_tree_live", AsyncMock(return_value=({}, {}))) as live_scan,
        ):
            response = await import_tree.get_import_tree(source_id="src-A")

        body = json.loads(response.body)
        assert body["storage_type"] == "live_walk"
        live_scan.assert_awaited_once_with("src-A")
        auto_trigger.assert_awaited_once_with("src-A")

    async def test_default_source_resolved_when_source_id_omitted(self):
        with (
            patch(
                "api.codebase_analytics.source_storage.get_default_source_id",
                AsyncMock(return_value="default-src"),
            ),
            patch.object(import_tree, "_load_import_tree_from_index", AsyncMock(return_value=({}, {}))) as loader,
        ):
            await import_tree.get_import_tree(source_id=None)

        loader.assert_awaited_once_with("default-src")


class TestLiveWalkFallbackStillScoped:
    """Regression guard: the fallback path must still honour #12330 scoping
    (resolve_scan_root), not silently widen to the whole AutoBot tree."""

    async def test_live_scan_uses_resolved_source_root(self, tmp_path):
        root_a = tmp_path / "proj_a"
        root_a.mkdir()
        _write_module(root_a, "mod_a.py", "import os\n")

        async def fake_resolve(source_id, use_default=True):
            return root_a if source_id == "A" else tmp_path

        with patch.object(import_tree, "resolve_scan_root", side_effect=fake_resolve):
            file_imports, _file_imported_by = await import_tree._scan_import_tree_live("A")

        assert "mod_a.py" in file_imports
