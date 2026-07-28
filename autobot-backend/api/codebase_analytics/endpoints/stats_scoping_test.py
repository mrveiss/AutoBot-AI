# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression test for Issue #12399 (sibling of #12393/#12398).

``stats._fetch_problems_from_chromadb`` validates indexed problem paths
against a root that falls back to ``get_project_root()`` (hardcoded
``parents[4]``) when no ``source_root`` was resolved. In the deployed
standalone rsync layout ``parents[4]`` resolves to ``/opt/autobot`` -- not
the analyzable repo -- so the fallback must instead use
``resolve_project_root()`` (git-walk-up / deployed ``code_source`` probe,
#10730), matching the fix already applied to ``resolve_scan_root`` (#12393)
and ``report._fetch_problems_from_chromadb`` (#12399).
"""

from unittest.mock import MagicMock, patch


class TestFetchProblemsFromChromaDBFallback:
    """Issue #12399: sibling of #12393's resolve_scan_root fix."""

    def test_unresolved_fallback_uses_deployed_layout_aware_root(self, tmp_path):
        """When source_root is None, path validation must resolve against
        resolve_project_root(), not the plain parents[4] get_project_root()."""
        from api.codebase_analytics.endpoints import stats as stats_mod

        deployed_root = tmp_path / "opt_autobot" / "code_source"
        wrong_root = tmp_path / "opt_autobot"
        captured: dict = {}

        def fake_filter(problems, root):
            captured["root"] = root
            return problems

        fake_collection = MagicMock()

        with (
            patch.object(
                stats_mod,
                "get_all_paginated",
                return_value={"metadatas": [{"file_path": "x.py"}]},
            ),
            patch.object(stats_mod, "filter_problems_by_file_existence", side_effect=fake_filter),
            patch.object(stats_mod, "resolve_project_root", return_value=str(deployed_root)),
        ):
            stats_mod._fetch_problems_from_chromadb(
                fake_collection, problem_type=None, source_id=None, source_root=None
            )

        assert captured["root"] == deployed_root
        assert captured["root"] != wrong_root
