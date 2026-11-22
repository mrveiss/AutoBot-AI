# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The report scans the selected source's checkout and never substitutes the install tree (#20513)."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
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


# --- review (#22092): contrast against the fallbacks the old code took ----------------------------------

_SENTINEL = Path("/SENTINEL/not-the-source")


@pytest.fixture
def install_tree_sentinels(tmp_path):
    """Everything the old code could fall back to points at a sentinel; the source's root is tmp_path."""
    fallbacks = SimpleNamespace(BACKEND_DIR=_SENTINEL, PROJECT_ROOT=_SENTINEL)
    with (
        patch.object(report_mod, "PATH", fallbacks, create=True),
        # the old identity check: the source root IS the install's git root
        patch.object(report_mod, "resolve_git_repo_root", lambda: str(tmp_path), create=True),
    ):
        yield tmp_path


@pytest.mark.asyncio
async def test_pattern_analysis_scans_the_source_root_not_the_backend_dir(install_tree_sentinels):
    analyzer = MagicMock()
    analyzer.analyze_directory = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(report_mod, "CodePatternAnalyzer", return_value=analyzer):
        await report_mod._get_pattern_analysis(project_root=install_tree_sentinels)
    scanned = analyzer.analyze_directory.call_args.args[0]
    assert scanned == str(install_tree_sentinels) and "SENTINEL" not in scanned


@pytest.mark.asyncio
async def test_bug_prediction_reads_the_source_root_not_the_project_root(install_tree_sentinels):
    predictor = MagicMock()
    predictor.analyze_directory_async = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(report_mod, "BugPredictor", return_value=predictor) as predictor_class:
        await report_mod._get_bug_prediction(str(install_tree_sentinels), "src-1")
    assert predictor_class.call_args.kwargs["project_root"] == str(install_tree_sentinels)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _SCANNERS)
async def test_a_scanner_called_without_a_root_is_a_type_error(name):
    with pytest.raises(TypeError):
        await getattr(report_mod, name)()


@pytest.mark.asyncio
async def test_bug_prediction_requires_its_source():
    with pytest.raises(TypeError):
        await report_mod._get_bug_prediction("/some/root")


@pytest.mark.asyncio
async def test_the_quality_health_request_carries_the_source():
    from api import analytics_reporting

    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={})
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    with patch.object(analytics_reporting, "get_http_client", return_value=client):
        await analytics_reporting.fetch_quality_health("src-1")
    assert client.get.await_args.kwargs["params"] == {"source_id": "src-1"}
