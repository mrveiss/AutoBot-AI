# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20493: the code-smell scan reaches nested files and its counts come from one list."""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from code_intelligence.anti_pattern_detection import analyzer as _analyzer_module
from code_intelligence.anti_pattern_detection.analyzer import AntiPatternSuiteAnalyzer

_SHARED_DIR = Path(__file__).resolve().parent / "shared"


def _load_real(leaf: str, monkeypatch: pytest.MonkeyPatch):
    """Load shared/<leaf>.py from its file, whatever sys.modules holds for it.

    The top-level conftest stubs ``code_intelligence`` submodules as MagicMocks,
    and another test can leave one installed. The analyzer binds
    ``get_ast_with_content`` / ``get_python_files`` at import, so a stub present
    then makes every file on the cached path raise. Loading by path leaves
    sys.modules as it was once the test ends (dataclasses need the module
    registered while it executes, so it is installed through monkeypatch).
    """
    name = f"_real_20493_{leaf}"
    spec = importlib.util.spec_from_file_location(name, _SHARED_DIR / f"{leaf}.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def real_shared_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the analyzer's cached path at the real AST and file-list caches.

    ``raising=False``: when the analyzer was first imported while the shared
    caches were stubbed out, its ImportError branch never bound these names.
    """
    monkeypatch.setattr(
        _analyzer_module,
        "get_ast_with_content",
        _load_real("ast_cache", monkeypatch).get_ast_with_content,
        raising=False,
    )
    monkeypatch.setattr(
        _analyzer_module,
        "get_cached_python_files",
        _load_real("file_cache", monkeypatch).get_python_files,
        raising=False,
    )
    monkeypatch.setattr(_analyzer_module, "HAS_SHARED_CACHE", True)


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


def test_cached_and_uncached_discovery_agree(tree: Path, real_shared_caches: None):
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


def test_files_failed_on_cached_path(tree: Path, real_shared_caches: None):
    a = AntiPatternSuiteAnalyzer()
    report = asyncio.run(a._analyze_directory_with_cache(str(tree)))
    assert report.total_files == 4
    assert report.files_failed == 1
    assert report.to_dict()["files_examined"] == 3


def test_custom_exclude_dirs_agree_across_paths(tree: Path):
    """exclude_dirs omitting a SKIP_DIRS name is authoritative on both paths."""
    a = AntiPatternSuiteAnalyzer(exclude_dirs=["pkg"])  # node_modules NOT excluded
    sync_files = a._get_python_files(str(tree))
    cached_files = asyncio.run(a._get_python_files_async(str(tree)))
    rel = {Path(f).relative_to(tree).as_posix() for f in sync_files}
    assert rel == {"top.py", "node_modules/x.py"}
    assert sync_files == cached_files


def test_out_of_root_path_is_excluded(tmp_path: Path):
    from code_intelligence.python_files import is_excluded

    assert is_excluded(Path("/elsewhere/a.py"), tmp_path, ["venv"]) is True
