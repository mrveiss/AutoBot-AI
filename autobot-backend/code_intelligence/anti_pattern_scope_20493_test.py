# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20493: the code-smell scan reaches nested files and its counts come from one list."""

import asyncio
from pathlib import Path

import pytest

from code_intelligence.anti_pattern_detection.analyzer import AntiPatternSuiteAnalyzer

_LONG_PARAMS = "def f(a, b, c, d, e, f, g, h, i, j, k, l):\n    return a\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """top.py, pkg/mid.py, pkg/sub/deep.py, plus a broken file and a skipped dir."""
    for rel in ("top.py", "pkg/mid.py", "pkg/sub/deep.py"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(_LONG_PARAMS, encoding="utf-8")
    (tmp_path / "pkg" / "broken.py").write_text("def (:\n", encoding="utf-8")
    skipped = tmp_path / "node_modules" / "x.py"
    skipped.parent.mkdir()
    skipped.write_text(_LONG_PARAMS, encoding="utf-8")
    return tmp_path


def test_control_fixture_has_nested_files(tree: Path):
    depths = {len(p.relative_to(tree).parts) for p in tree.rglob("*.py")}
    assert max(depths) >= 3 and 1 in depths


def test_nested_files_are_scanned(tree: Path):
    report = AntiPatternSuiteAnalyzer().analyze_directory(str(tree))
    scanned = {Path(p.file_path).relative_to(tree).as_posix() for p in report.anti_patterns}
    assert {"top.py", "pkg/mid.py", "pkg/sub/deep.py"} <= scanned
    assert not any(s.startswith("node_modules") for s in scanned)


def test_cached_and_uncached_discovery_agree(tree: Path):
    a = AntiPatternSuiteAnalyzer()
    sync_files = a._get_python_files(str(tree))
    cached_files = asyncio.run(a._get_python_files_async(str(tree)))
    assert sync_files == cached_files
    assert len(sync_files) == 4  # three clean files + broken.py; node_modules skipped


def test_root_below_an_excluded_name_is_still_scanned(tmp_path: Path):
    root = tmp_path / "venv" / "proj"
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / "m.py").write_text(_LONG_PARAMS, encoding="utf-8")
    assert len(AntiPatternSuiteAnalyzer()._get_python_files(str(root))) == 1


def test_summary_equals_list_after_filtering(tree: Path):
    report = AntiPatternSuiteAnalyzer().analyze_directory(str(tree))
    assert report.anti_patterns
    report.anti_patterns = report.anti_patterns[:1]  # what the endpoint's severity filter does
    out = report.to_dict()
    assert out["total_issues"] == len(out["anti_patterns"]) == 1
    assert sum(out["summary"].values()) == len(out["anti_patterns"])
    assert sum(out["severity_distribution"].values()) == len(out["anti_patterns"])


def test_scope_is_stated(tree: Path):
    out = AntiPatternSuiteAnalyzer().analyze_directory(str(tree)).to_dict()
    assert out["total_files"] == 4
    assert out["files_failed"] == 1
    assert out["files_examined"] == 3
    assert out["cap_applied"] is False
