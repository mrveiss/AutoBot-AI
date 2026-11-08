# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21004: every code-intelligence analyzer discovers files and excludes dirs in one place."""

import ast
import importlib.util
from pathlib import Path
from typing import List

import pytest

_PKG = Path(__file__).resolve().parent
_CANONICAL = "python_files.py"
_WALKS = {"rglob", "walk"}
_COPY_NAMES = {"EXCLUDE_DIRS", "DEFAULT_EXCLUDE_DIRS", "_SKIP_DIRS", "_COCHANGE_SKIP_DIRS"}


def _load_real_module():
    """Load python_files.py by path (conftest stubs code_intelligence submodules)."""
    spec = importlib.util.spec_from_file_location("_real_21004_python_files", _PKG / _CANONICAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_files(root: Path) -> List[Path]:
    """Non-test ``.py`` files below *root*, excluding the canonical module."""
    return sorted(
        p
        for p in root.rglob("*.py")  # noqa: bare-walk (the guard's own scan)
        if p.name != _CANONICAL and not p.name.endswith("_test.py") and "tests" not in p.relative_to(root).parts
    )


def find_violations(root: Path) -> List[str]:
    """``file:line what`` for each bare walk call or analyzer-local exclusion-set copy."""
    found: List[str] = []
    for path in _production_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in _WALKS and (node.func.attr == "rglob" or _is_os_walk(node.func)):
                    found.append(f"{path.relative_to(root)}:{node.lineno} bare {node.func.attr}()")
            for name in _assigned_names(node):
                if name in _COPY_NAMES:
                    found.append(f"{path.relative_to(root)}:{node.lineno} local {name}")
    return found


def _is_os_walk(func: ast.Attribute) -> bool:
    return isinstance(func.value, ast.Name) and func.value.id == "os"


def _assigned_names(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def test_no_bare_walk_or_exclusion_copy_in_code_intelligence():
    assert find_violations(_PKG) == []


def test_guard_flags_a_planted_bare_walk_and_copy(tmp_path: Path):
    """Control: a clean run proves nothing unless the guard sees a planted violation."""
    (tmp_path / "planted.py").write_text(
        "import os\nEXCLUDE_DIRS = {'x'}\n\ndef f(p):\n    list(p.rglob('*.py'))\n    return os.walk(p)\n",
        encoding="utf-8",
    )
    found = find_violations(tmp_path)
    assert len(found) == 3
    assert (
        any("rglob" in f for f in found) and any("walk" in f for f in found) and any("EXCLUDE_DIRS" in f for f in found)
    )


@pytest.mark.parametrize("skipped_ancestor", ["venv", "node_modules", ".worktrees"])
def test_root_under_a_skipped_name_still_yields_files(tmp_path: Path, skipped_ancestor: str):
    root = tmp_path / skipped_ancestor / "project"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "venv").mkdir()
    (root / "venv" / "skipped.py").write_text("y = 2\n", encoding="utf-8")
    module = _load_real_module()
    assert [p.name for p in module.discover_files(root)] == ["a.py"]
    assert [Path(p).name for p in module.collect_python_files(str(root), module.ANALYSIS_EXCLUDE_DIRS)] == ["a.py"]


def test_analysis_exclude_dirs_derives_from_skip_dirs():
    from utils.file_categorization import SKIP_DIRS

    assert SKIP_DIRS <= _load_real_module().ANALYSIS_EXCLUDE_DIRS
