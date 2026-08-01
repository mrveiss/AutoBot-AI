# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for cross-project analytics data leakage (Issue #12330).

Several Codebase Analytics endpoints accepted a ``source_id`` "for API
consistency" but ignored it, scanning AutoBot's own project root regardless of
the selected code source. As a result opening one project's analytics could
show another project's call graph / endpoint coverage / dependency graph.

These tests assert the scoping fix: a request for project A can never see
project B's data, while a same-project request still works.

Issue #12359 extends this coverage to the dependency graph's ChromaDB module
load (``_load_modules_from_chromadb``) and the environment/hardcode-analysis
per-source cache, and asserts the env scan-root helper is aligned with
``resolve_scan_root`` (used by call-graph/import-tree/dependencies) so a
``source_id=None`` request resolves the caller's DEFAULT source rather than
falling straight through to the AutoBot project root.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _write_module(directory: Path, filename: str, body: str) -> None:
    (directory / filename).write_text(body, encoding="utf-8")


class TestResolveScanRoot:
    """Unit tests for the shared source-scoping helper."""

    async def test_scopes_to_requested_source(self, tmp_path):
        """Different source_ids resolve to their own clone paths (no shared root)."""
        from api.codebase_analytics.endpoints import shared

        root_a = tmp_path / "proj_a"
        root_b = tmp_path / "proj_b"
        root_a.mkdir()
        root_b.mkdir()

        async def fake_resolve(source_id):
            return {"A": root_a, "B": root_b}.get(source_id)

        with patch.object(shared, "resolve_source_root", side_effect=fake_resolve):
            resolved_a = await shared.resolve_scan_root("A")
            resolved_b = await shared.resolve_scan_root("B")

        assert resolved_a == root_a
        assert resolved_b == root_b
        assert resolved_a != resolved_b

    async def test_falls_back_to_project_root_when_unresolved(self):
        """No source and no default → AutoBot project root (legacy behavior)."""
        from api.codebase_analytics.endpoints import shared

        with (
            patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)),
            patch(
                "api.codebase_analytics.source_storage.get_default_source_id",
                AsyncMock(return_value=None),
            ),
        ):
            resolved = await shared.resolve_scan_root(None)

        assert resolved == shared.get_project_root()

    async def test_unresolved_fallback_uses_deployed_layout_aware_root(self, tmp_path):
        """Issue #12393: unresolved-source fallback must use resolve_project_root()
        (git-walk-up / deployed code_source probe, #10730), not the plain
        parents[4] get_project_root() -- which resolves to /opt/autobot (not the
        analyzable repo) in the deployed standalone rsync layout."""
        from api.codebase_analytics.endpoints import shared

        deployed_root = tmp_path / "opt_autobot" / "code_source"
        wrong_root = tmp_path / "opt_autobot"

        with (
            patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)),
            patch(
                "api.codebase_analytics.source_storage.get_default_source_id",
                AsyncMock(return_value=None),
            ),
            patch.object(shared, "resolve_project_root", return_value=str(deployed_root)),
            patch.object(shared, "get_project_root", return_value=wrong_root),
        ):
            resolved = await shared.resolve_scan_root(None)

        assert resolved == deployed_root
        assert resolved != wrong_root

    async def test_uses_default_source_when_source_id_missing(self, tmp_path):
        """When no source_id is given the default source is scoped, not the global root."""
        from api.codebase_analytics.endpoints import shared

        default_root = tmp_path / "default_proj"
        default_root.mkdir()

        async def fake_resolve(source_id):
            return default_root if source_id == "DEFAULT" else None

        with (
            patch.object(shared, "resolve_source_root", side_effect=fake_resolve),
            patch(
                "api.codebase_analytics.source_storage.get_default_source_id",
                AsyncMock(return_value="DEFAULT"),
            ),
        ):
            resolved = await shared.resolve_scan_root(None)

        assert resolved == default_root


class TestCallGraphIsolation:
    """End-to-end: the call graph returned for A must not contain B's code."""

    async def test_call_graph_scoped_to_source(self, tmp_path):
        from api.codebase_analytics.endpoints import call_graph, shared

        root_a = tmp_path / "proj_a"
        root_b = tmp_path / "proj_b"
        root_a.mkdir()
        root_b.mkdir()
        _write_module(root_a, "mod_a.py", "def alpha_unique_fn():\n    return 1\n")
        _write_module(root_b, "mod_b.py", "def beta_unique_fn():\n    return 2\n")

        async def fake_resolve(source_id):
            return {"A": root_a, "B": root_b}.get(source_id)

        # Scope resolution to our temp sources; cache writes are best-effort and
        # swallowed if Redis is unavailable, so no Redis is required.
        with patch.object(shared, "resolve_source_root", side_effect=fake_resolve):
            resp_a = await call_graph.get_call_graph(refresh=True, source_id="A")
            resp_b = await call_graph.get_call_graph(refresh=True, source_id="B")

        names_a = _all_function_names(resp_a)
        names_b = _all_function_names(resp_b)

        # Same-project data is present...
        assert "alpha_unique_fn" in names_a
        assert "beta_unique_fn" in names_b
        # ...and cross-project data never leaks across the boundary.
        assert "beta_unique_fn" not in names_a
        assert "alpha_unique_fn" not in names_b


class TestEndpointCoverageCacheScoping:
    """The endpoint-coverage in-memory cache must be keyed per source."""

    async def test_cache_key_is_per_source(self):
        from api.codebase_analytics.endpoints.api_endpoints import _cache_key

        assert _cache_key(None) == "default"
        assert _cache_key("A") == "A"
        assert _cache_key("A") != _cache_key("B")

    async def test_analysis_cached_and_not_shared_between_sources(self, tmp_path):
        from api.codebase_analytics.endpoints import api_endpoints

        root_a = tmp_path / "cov_a"
        root_b = tmp_path / "cov_b"
        root_a.mkdir()
        root_b.mkdir()

        async def fake_resolve(source_id, use_default=True):
            return {"A": root_a, "B": root_b}.get(source_id, api_endpoints.Path("/tmp"))

        analysis_a = MagicMock(name="analysis_A")
        analysis_b = MagicMock(name="analysis_B")

        def fake_checker(project_root=None):
            checker = MagicMock()
            checker.run_full_analysis = MagicMock(return_value=analysis_a if project_root == root_a else analysis_b)
            return checker

        api_endpoints._analysis_cache.clear()
        with (
            patch.object(api_endpoints, "resolve_scan_root", side_effect=fake_resolve),
            patch.object(api_endpoints, "_get_checker", side_effect=fake_checker),
        ):
            result_a = await api_endpoints._get_or_run_analysis("A")
            result_b = await api_endpoints._get_or_run_analysis("B")
            # Second call for A must hit the per-source cache (no re-scan).
            cached_a = await api_endpoints._get_or_run_analysis("A")

        assert result_a is analysis_a
        assert result_b is analysis_b
        assert result_a is not result_b
        assert cached_a is analysis_a
        assert api_endpoints._analysis_cache["A"] is analysis_a
        assert api_endpoints._analysis_cache["B"] is analysis_b


class TestDependencyModuleLoadIsolation:
    """_load_modules_from_chromadb must scope its ChromaDB where-filter by
    source_id so one project's ChromaDB-indexed modules never appear in
    another project's dependency graph (Issue #12359)."""

    async def test_where_filter_includes_source_id(self):
        from api.codebase_analytics.endpoints import dependencies as deps

        captured: dict = {}

        def fake_get_all_paginated(collection, where=None, include=None):
            captured["where"] = where
            return {"metadatas": []}

        with patch.object(deps, "get_all_paginated", side_effect=fake_get_all_paginated):
            await deps._load_modules_from_chromadb(MagicMock(), {}, source_id="A")

        assert captured["where"] == {"$and": [{"type": {"$in": ["function", "class"]}}, {"source_id": "A"}]}

    async def test_source_b_load_never_returns_source_a_modules(self):
        """Simulates real ChromaDB filtering to prove no cross-source bleed."""
        from api.codebase_analytics.endpoints import dependencies as deps

        all_metadatas = [
            {"type": "function", "file_path": "a/mod_a.py", "source_id": "A"},
            {"type": "function", "file_path": "b/mod_b.py", "source_id": "B"},
        ]

        def fake_get_all_paginated(collection, where=None, include=None):
            wanted = where["$and"][1]["source_id"]
            return {"metadatas": [m for m in all_metadatas if m["source_id"] == wanted]}

        modules_a: dict = {}
        modules_b: dict = {}
        with patch.object(deps, "get_all_paginated", side_effect=fake_get_all_paginated):
            await deps._load_modules_from_chromadb(MagicMock(), modules_a, source_id="A")
            await deps._load_modules_from_chromadb(MagicMock(), modules_b, source_id="B")

        assert "a/mod_a.py" in modules_a
        assert "b/mod_b.py" not in modules_a
        assert "b/mod_b.py" in modules_b
        assert "a/mod_a.py" not in modules_b


class TestEnvironmentCacheScoping:
    """The env-analysis cache must be keyed per source, and the scan root
    helper must be aligned with the sibling scan-root-scoped endpoints
    (Issue #12359)."""

    def test_cache_key_is_per_source(self):
        from api.codebase_analytics.endpoints.environment import _env_cache_key

        assert _env_cache_key(None) == "default"
        assert _env_cache_key("A") == "A"
        assert _env_cache_key("A") != _env_cache_key("B")

    async def test_two_sources_use_distinct_cache_entries(self):
        """Analysis cached for source A must never surface under source B's key."""
        from api.codebase_analytics.endpoints import environment

        environment._env_analysis_cache.clear()
        environment._env_analysis_cache["A"] = {"total_hardcoded_values": 1, "marker": "A"}
        environment._env_analysis_cache["B"] = {"total_hardcoded_values": 2, "marker": "B"}

        cached_a = await environment._check_env_analysis_cache(use_llm_filter=False, refresh=False, source_id="A")
        cached_b = await environment._check_env_analysis_cache(use_llm_filter=False, refresh=False, source_id="B")

        data_a = json.loads(cached_a.body)
        data_b = json.loads(cached_b.body)
        assert data_a["marker"] == "A"
        assert data_b["marker"] == "B"

    async def test_scan_root_resolves_default_source_for_none(self, tmp_path):
        """Issue #12359: _resolve_env_scan_root now delegates to the shared
        resolve_scan_root (used by call-graph/import-tree/dependencies), so a
        source_id=None request resolves the caller's DEFAULT registered
        source instead of jumping straight to the AutoBot project root."""
        from api.codebase_analytics.endpoints import environment, shared

        default_root = tmp_path / "default_proj"
        default_root.mkdir()

        async def fake_resolve_source_root(source_id):
            return default_root if source_id == "DEFAULT" else None

        with (
            patch.object(shared, "resolve_source_root", side_effect=fake_resolve_source_root),
            patch(
                "api.codebase_analytics.source_storage.get_default_source_id",
                AsyncMock(return_value="DEFAULT"),
            ),
        ):
            resolved = await environment._resolve_env_scan_root(None)

        assert resolved == str(default_root)

    async def test_explicit_source_id_unchanged_by_alignment(self, tmp_path):
        """A real, resolvable source_id resolves identically whether via
        resolve_source_root directly (pre-fix) or via resolve_scan_root
        (post-fix). Behavior differs only in two cases: source_id=None (now
        resolves the DEFAULT source), and an UNRESOLVABLE source (fallback root
        is now get_project_root() vs the old resolve_project_root(); identical
        in a dev checkout, differs in the deployed layout -- tracked in #12393)."""
        from api.codebase_analytics.endpoints import environment, shared

        root_a = tmp_path / "proj_a"
        root_a.mkdir()

        async def fake_resolve_source_root(source_id):
            return root_a if source_id == "A" else None

        with patch.object(shared, "resolve_source_root", side_effect=fake_resolve_source_root):
            resolved = await environment._resolve_env_scan_root("A")

        assert resolved == str(root_a)


def _all_function_names(response) -> set:
    """Collect every function name from a call-graph JSONResponse."""
    data = json.loads(response.body)
    graph = data.get("call_graph", {})
    names = {node.get("name") for node in graph.get("nodes", [])}
    names |= {node.get("name") for node in data.get("orphaned_functions", [])}
    return names
