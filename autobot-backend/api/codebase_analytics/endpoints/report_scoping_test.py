# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for cross-project data leakage in the codebase report
pipeline (Issue #12372).

``GET /report`` receives ``source_id`` and correctly scopes the *problems*
fetch (``_fetch_problems_from_chromadb``) to it, but every sub-analysis it
runs -- bug prediction, API-endpoint coverage, duplicate-code detection,
cross-language patterns, and code-pattern analysis -- ignored ``source_id``
and always scanned AutoBot's own project root / a hard-coded backend
directory. A report requested for source B could therefore surface
AutoBot's own (or another source's) findings in every analysis section.

This mirrors the #12356/#12374 fix already applied to the dedicated
cross-language-patterns endpoints: thread ``source_id``/the resolved scan
root through every sub-analysis so a report for one source never scans or
returns another source's (or AutoBot's own) tree.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _build_analysis_task_list: every sub-analysis must receive the resolved
# source_id / scan_root, not silently default to AutoBot's own root.
# ---------------------------------------------------------------------------
class TestBuildAnalysisTaskListScoping:
    """Issue #12372: task construction must thread source scoping through."""

    async def test_all_sub_analyses_receive_source_id_and_scan_root(self):
        from api.codebase_analytics.endpoints import report as report_mod

        scan_root = Path("/tmp/proj_b")
        captured: dict = {}

        # Issue #12372 test note: report._get_* are async functions, so
        # ``patch.object`` auto-detects them and installs ``AsyncMock``.
        # AsyncMock only invokes ``side_effect`` when the returned coroutine
        # is *awaited* -- calling the patched function merely schedules that
        # execution. The task list must therefore be awaited, not just
        # constructed, to observe what each sub-analysis was called with.
        def fake_bug_prediction(project_root=None, use_semantic=False):
            captured["bug_prediction"] = {"project_root": project_root, "use_semantic": use_semantic}
            return None

        def fake_api_endpoint(project_root=None):
            captured["api_endpoint"] = {"project_root": project_root}
            return None

        def fake_duplicate(project_root=None):
            captured["duplicate"] = {"project_root": project_root}
            return None

        def fake_cross_language(source_id=None, project_root=None):
            captured["cross_language"] = {"source_id": source_id, "project_root": project_root}
            return None

        def fake_pattern_analysis(project_root=None):
            captured["pattern_analysis"] = {"project_root": project_root}
            return None

        with (
            patch.object(report_mod, "_get_bug_prediction", side_effect=fake_bug_prediction),
            patch.object(report_mod, "_get_api_endpoint_analysis", side_effect=fake_api_endpoint),
            patch.object(report_mod, "_get_duplicate_analysis", side_effect=fake_duplicate),
            patch.object(report_mod, "_get_cross_language_analysis", side_effect=fake_cross_language),
            patch.object(report_mod, "_get_pattern_analysis", side_effect=fake_pattern_analysis),
        ):
            tasks = report_mod._build_analysis_task_list(
                include_bug_prediction=True,
                include_api_analysis=True,
                include_duplicate_analysis=True,
                include_cross_language_analysis=True,
                include_pattern_analysis=True,
                use_semantic=False,
                source_id="B",
                scan_root=scan_root,
            )
            for _name, coro in tasks:
                await coro

        # None of the sub-analyses fall back to AutoBot's own root/no source.
        assert captured["bug_prediction"]["project_root"] == str(scan_root)
        assert captured["api_endpoint"]["project_root"] == scan_root
        assert captured["duplicate"]["project_root"] == scan_root
        assert captured["cross_language"]["project_root"] == scan_root
        assert captured["cross_language"]["source_id"] == "B"
        assert captured["pattern_analysis"]["project_root"] == scan_root


# ---------------------------------------------------------------------------
# End-to-end: GET /report for source B must never scan/return source A's
# (or AutoBot's own) tree.
# ---------------------------------------------------------------------------
class TestReportPipelineSourceIsolation:
    """Issue #12372: a report for source B must not surface source A's data."""

    async def _run_report_for_source(self, source_id, source_roots, captured):
        from api.codebase_analytics.endpoints import report as report_mod

        async def fake_resolve_source_root(sid):
            return source_roots.get(sid)

        async def fake_get_cross_language_analysis(source_id=None, project_root=None):
            captured.setdefault(source_id, {})["cross_language_root"] = project_root
            return None

        async def fake_get_duplicate_analysis(project_root=None):
            captured.setdefault(source_id, {})["duplicate_root"] = project_root
            return None

        async def fake_get_pattern_analysis(project_root=None):
            captured.setdefault(source_id, {})["pattern_root"] = project_root
            return None

        async def fake_get_api_endpoint_analysis(project_root=None):
            captured.setdefault(source_id, {})["api_root"] = project_root
            return None

        async def fake_get_bug_prediction(project_root=None, use_semantic=False):
            captured.setdefault(source_id, {})["bug_root"] = project_root
            return None

        with (
            patch.object(report_mod, "resolve_source_root", side_effect=fake_resolve_source_root),
            patch.object(
                report_mod,
                "_fetch_problems_from_chromadb",
                return_value=[],
            ),
            patch.object(
                report_mod,
                "_get_cross_language_analysis",
                side_effect=fake_get_cross_language_analysis,
            ),
            patch.object(report_mod, "_get_duplicate_analysis", side_effect=fake_get_duplicate_analysis),
            patch.object(report_mod, "_get_pattern_analysis", side_effect=fake_get_pattern_analysis),
            patch.object(
                report_mod,
                "_get_api_endpoint_analysis",
                side_effect=fake_get_api_endpoint_analysis,
            ),
            patch.object(report_mod, "_get_bug_prediction", side_effect=fake_get_bug_prediction),
        ):
            await report_mod.generate_analysis_report(source_id=source_id, quick=False)

    async def test_source_b_report_scans_only_source_b_root(self):
        """A report for source B must resolve/scan source B's root, never A's."""
        root_a = Path("/srv/sources/a")
        root_b = Path("/srv/sources/b")
        source_roots = {"A": root_a, "B": root_b}
        captured: dict = {}

        await self._run_report_for_source("A", source_roots, captured)
        await self._run_report_for_source("B", source_roots, captured)

        # Each source's sub-analyses see only that source's resolved root.
        assert captured["A"]["cross_language_root"] == root_a
        assert captured["B"]["cross_language_root"] == root_b
        assert captured["A"]["cross_language_root"] != captured["B"]["cross_language_root"]

        for key in ("duplicate_root", "pattern_root", "api_root"):
            assert captured["A"][key] == root_a
            assert captured["B"][key] == root_b

        # Bug prediction receives the root as a string (its own signature).
        assert captured["A"]["bug_root"] == str(root_a)
        assert captured["B"]["bug_root"] == str(root_b)

    async def test_unresolvable_source_falls_back_to_project_root_not_none(self):
        """No registered source resolves -> fall back to AutoBot's own root,
        not None (which would crash str(None) downstream / silently point
        every sub-analysis at an undefined scope)."""
        from api.codebase_analytics.endpoints import report as report_mod
        from api.codebase_analytics.endpoints.shared import get_project_root

        captured: dict = {}

        async def fake_get_pattern_analysis(project_root=None):
            captured["pattern_root"] = project_root
            return None

        with (
            patch.object(report_mod, "resolve_source_root", new=AsyncMock(return_value=None)),
            patch.object(report_mod, "_fetch_problems_from_chromadb", return_value=[]),
            patch.object(report_mod, "_get_cross_language_analysis", new=AsyncMock(return_value=None)),
            patch.object(report_mod, "_get_duplicate_analysis", new=AsyncMock(return_value=None)),
            patch.object(report_mod, "_get_pattern_analysis", side_effect=fake_get_pattern_analysis),
            patch.object(report_mod, "_get_api_endpoint_analysis", new=AsyncMock(return_value=None)),
            patch.object(report_mod, "_get_bug_prediction", new=AsyncMock(return_value=None)),
        ):
            await report_mod.generate_analysis_report(source_id="unresolvable-source", quick=False)

        assert captured["pattern_root"] == get_project_root()


# ---------------------------------------------------------------------------
# Write-side leak: the report path must NOT persist the scanned source's code
# into the global, source-unscoped `code_patterns` ChromaDB collection (#12372
# review item c). Now that _get_pattern_analysis scans arbitrary source roots,
# embedding storage must be disabled so one source's code isn't written into a
# shared store another source's report could read (read-side filter → #12384).
# ---------------------------------------------------------------------------
class TestPatternAnalysisNoGlobalWrite:
    """Issue #12372: _get_pattern_analysis must disable embedding storage."""

    async def test_get_pattern_analysis_disables_embedding_storage(self):
        from api.codebase_analytics.endpoints import report as report_mod

        captured: dict = {}

        def fake_analyzer(**kwargs):
            captured.update(kwargs)
            analyzer = MagicMock()
            # Stop right after construction — we only assert the kwargs; a raise
            # routes through _get_pattern_analysis's except → returns None.
            analyzer.analyze_directory = AsyncMock(side_effect=RuntimeError("stop"))
            return analyzer

        with patch.object(report_mod, "CodePatternAnalyzer", side_effect=fake_analyzer):
            result = await report_mod._get_pattern_analysis(project_root="/srv/sources/b")

        assert result is None  # analyze stopped; no crash
        # The report consumes the returned object directly and never reads the
        # ChromaDB cache, so persistence must be OFF to avoid a cross-source write.
        assert captured.get("enable_embedding_storage") is False
