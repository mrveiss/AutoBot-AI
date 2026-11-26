# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pattern analyzer stops at its cancel token, and the report route signals it (#22094)."""

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from api.codebase_analytics.endpoints import report as report_mod
from code_intelligence.fingerprinting.detector import CloneDetector
from testkit.real_pattern_analysis import load_real_pattern_analysis_package
from utils.cancel_tokens import CancelTokenSet

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


def _clone_analyzer(detector: CloneDetector, token=None) -> CodePatternAnalyzer:
    analyzer = _analyzer(token)
    analyzer._clone_detector = detector
    return analyzer


def _slow_files(detector: CloneDetector, seen: list, done: threading.Event):
    """Patches: each file takes 50 ms in the thread, and ``done`` is set when the thread's scan returns or raises."""
    extract, detect = detector._extract_fragments, detector.detect_clones

    def slow_extract(path):
        seen.append(path)
        time.sleep(0.05)
        return extract(path)

    def detect_then_flag(*args):
        try:
            return detect(*args)
        finally:
            done.set()

    return patch.object(detector, "_extract_fragments", slow_extract), patch.object(
        detector, "detect_clones", detect_then_flag
    )


async def test_a_timeout_stops_the_clone_thread_before_its_last_file(tmp_path):
    """The clone thread scans the whole tree; abandoning its await must stop it, not just the wait."""
    _tree(tmp_path, 40)
    detector, seen, done = CloneDetector(), [], threading.Event()
    analyzer = _clone_analyzer(detector, threading.Event())
    slow, flag = _slow_files(detector, seen, done)
    with slow, flag:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(analyzer._run_clone_detection(str(tmp_path)), timeout=0.2)
        assert await asyncio.to_thread(done.wait, 10)  # the thread returned, instead of walking on
    assert 0 < len(seen) < 40  # contrast below: unabandoned, it reads all forty
    assert not analyzer.cancel_token.is_set()  # a phase timeout skips the phase; it does not cancel the analysis


async def test_an_unabandoned_clone_thread_reads_every_file(tmp_path):
    _tree(tmp_path, 4)
    detector, seen, done = CloneDetector(), [], threading.Event()
    slow, flag = _slow_files(detector, seen, done)
    with slow, flag:
        result = await _clone_analyzer(detector)._run_clone_detection(str(tmp_path))
    assert len(seen) == 4 and "error" not in result


async def test_the_analysis_token_stops_the_clone_thread(tmp_path):
    _tree(tmp_path, 3)
    token = threading.Event()
    token.set()
    detector, seen, done = CloneDetector(), [], threading.Event()
    slow, flag = _slow_files(detector, seen, done)
    with slow, flag:
        with pytest.raises(CancelTokenSet):  # the thread stopped itself at the analysis token
            await _clone_analyzer(detector, token)._run_clone_detection(str(tmp_path))
    assert seen == []


async def test_an_analysis_stopped_at_its_token_answers_none(tmp_path):
    class Stopped:
        def __init__(self, **kwargs):
            pass

        async def analyze_directory(self, _directory):
            raise AnalysisCancelled("stopped at its token")

    with patch.object(report_mod, "CodePatternAnalyzer", Stopped):
        assert await report_mod._get_pattern_analysis(tmp_path) is None


async def test_an_outer_cancel_still_propagates_even_when_the_analysis_stops_at_its_token(tmp_path):
    started = asyncio.Event()

    class StopsOnCancel:
        def __init__(self, **kwargs):
            pass

        async def analyze_directory(self, _directory):
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise AnalysisCancelled("stopped while the caller was cancelled")

    with patch.object(report_mod, "CodePatternAnalyzer", StopsOnCancel):
        task = asyncio.create_task(report_mod._get_pattern_analysis(tmp_path))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
