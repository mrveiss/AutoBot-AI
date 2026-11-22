# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Source-root scoping of the stats ``/problems`` path validation (#12399, #20513).

``stats._fetch_problems_from_chromadb`` validates indexed problem paths against the
SOURCE'S root. It used to fall back to AutoBot's own tree when no root was
resolved; #20513 removed that fallback, so the root is required and a source with
no checkout is a 404 from the route.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestProblemsUseTheSourceRoot:
    def test_path_validation_resolves_against_the_source_root(self, tmp_path):
        from api.codebase_analytics.endpoints import stats as stats_mod

        source_root = tmp_path / "proj"
        captured: dict = {}

        def fake_filter(problems, root):
            captured["root"] = root
            return problems

        with (
            patch.object(stats_mod, "get_all_paginated", return_value={"metadatas": [{"file_path": "x.py"}]}),
            patch.object(stats_mod, "filter_problems_by_file_existence", side_effect=fake_filter),
        ):
            stats_mod._fetch_problems_from_chromadb(
                MagicMock(), problem_type=None, source_id="src1", source_root=source_root
            )

        assert captured["root"] == source_root

    async def test_a_source_with_no_checkout_is_a_404_not_autobots_tree(self):
        from api.codebase_analytics.endpoints import shared
        from api.codebase_analytics.endpoints import stats as stats_mod

        with patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)):
            with pytest.raises(shared.UnresolvedSourceError) as caught:
                await stats_mod.get_codebase_problems(source_id="ghost")

        assert caught.value.status_code == 404
