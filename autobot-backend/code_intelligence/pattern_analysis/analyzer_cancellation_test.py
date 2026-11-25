# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pattern analyzer stops at its cancel token, and the report route signals it (#22094)."""

import asyncio
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from api.codebase_analytics.endpoints import report as report_mod
from testkit.real_pattern_analysis import load_real_pattern_analysis_package

# The top-level conftest stubs ``code_intelligence.pattern_analysis``; load the real modules.
_pkg = load_real_pattern_analysis_package(Path(__file__).resolve().parent, "_real_pattern_analysis_cancel")
CodePatternAnalyzer = _pkg.analyzer.CodePatternAnalyzer
AnalysisCancelled = _pkg.cancellation.AnalysisCancelled


def _tree(root: Path, count: int = 3) -> None:
    for i in range(count):
        (root / f"m{i}.py").write_text("def f(a):\n    return a\n", encoding="utf-8")


def _analyzer(token=None) -> CodePatternAnalyzer:
    return CodePatternAnalyzer(
        enable_clone_detection=False,
        enable_anti_pattern_detection=False,
        enable_embedding_storage=False,
        cancel_token=token,
    )


async def test_a_token_set_before_the_run_analyses_no_file(tmp_path):
    _tree(tmp_path)
    token = threading.Event()
    token.set()
    analyzer = _analyzer(token)
    with patch.object(analyzer._complexity_analyzer, "analyze_file") as analyze_file:
        with pytest.raises(AnalysisCancelled):
            await analyzer.analyze_directory(str(tmp_path))
    analyze_file.assert_not_called()


async def test_a_token_set_mid_batch_stops_before_the_next_file(tmp_path):
    _tree(tmp_path, 5)
    token = threading.Event()
    analyzer = _analyzer(token)
    seen = []

    def analyze_file(path):
        seen.append(path)
        token.set()  # the caller stops waiting while the first file is being read

    with patch.object(analyzer._complexity_analyzer, "analyze_file", side_effect=analyze_file):
        with pytest.raises(AnalysisCancelled):
            await analyzer.analyze_directory(str(tmp_path))
    assert len(seen) == 1  # contrast: without the token every one of the five files is read


async def test_without_a_token_every_file_is_analysed(tmp_path):
    _tree(tmp_path, 5)
    analyzer = _analyzer()
    with patch.object(
        analyzer._complexity_analyzer, "analyze_file", wraps=analyzer._complexity_analyzer.analyze_file
    ) as spy:
        await analyzer.analyze_directory(str(tmp_path))
    assert spy.call_count == 5


async def test_the_report_signals_the_analyzer_token_when_its_deadline_fires(tmp_path):
    captured = {}

    class Slow:
        def __init__(self, **kwargs):
            captured["token"] = kwargs["cancel_token"]

        async def analyze_directory(self, _directory):
            await asyncio.sleep(60)

    real_wait_for = asyncio.wait_for

    async def short_wait_for(awaitable, timeout):
        return await real_wait_for(awaitable, timeout=0.01)

    with (
        patch.object(report_mod, "CodePatternAnalyzer", Slow),
        patch.object(report_mod.asyncio, "wait_for", short_wait_for),
    ):
        assert await report_mod._get_pattern_analysis(tmp_path) is None
    assert captured["token"].is_set()
