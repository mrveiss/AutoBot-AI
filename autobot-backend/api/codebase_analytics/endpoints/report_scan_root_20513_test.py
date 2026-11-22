# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The report scans the selected source's checkout and never substitutes the install tree (#20513)."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.codebase_analytics.endpoints import report as report_mod

_SCANNERS = (
    "_get_pattern_analysis",
    "_get_duplicate_analysis",
    "_get_api_endpoint_analysis",
    "_get_bug_prediction",
    "_get_cross_language_analysis",
)


@pytest.mark.parametrize("name", _SCANNERS)
def test_a_scanner_has_no_default_root(name):
    root = inspect.signature(getattr(report_mod, name)).parameters["project_root"]
    assert root.default is inspect.Parameter.empty, name


@pytest.mark.parametrize("name", ["_build_analysis_task_list", "_run_parallel_analyses", "_resolve_analyses"])
def test_the_plumbing_requires_its_source_and_root(name):
    params = inspect.signature(getattr(report_mod, name)).parameters
    assert params["source_id"].default is inspect.Parameter.empty
    assert params["scan_root"].default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_pattern_analysis_scans_the_sources_root_even_when_it_is_the_install_root(tmp_path):
    analyzer = MagicMock()
    analyzer.analyze_directory = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(report_mod, "CodePatternAnalyzer", return_value=analyzer):
        await report_mod._get_pattern_analysis(project_root=tmp_path)
    analyzer.analyze_directory.assert_called_once_with(str(tmp_path))


@pytest.mark.asyncio
async def test_duplicate_analysis_scans_the_sources_root(tmp_path):
    scan = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(report_mod, "_run_standard_analysis", scan):
        await report_mod._get_duplicate_analysis(project_root=tmp_path)
    assert scan.await_args.args[0] == str(tmp_path)
