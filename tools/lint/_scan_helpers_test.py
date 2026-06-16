# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/_scan_helpers.py — see #5449.

Pins the shared scan behavior used by ``check_no_utcnow_isoformat.py``
and ``check_no_kb_aioredis_access.py``. Covers the directories each
hook depends on being excluded (especially ``.worktrees`` — the drift
that motivated the extraction per #5394 and #5418).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Load the module-under-test directly (tools/lint is not a package).
_HELPER_PATH = Path(__file__).parent / "_scan_helpers.py"
_spec = importlib.util.spec_from_file_location("_scan_helpers_under_test", _HELPER_PATH)
assert _spec is not None and _spec.loader is not None
helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helpers)


def _make_tree(root: Path, rel_paths: list[str]) -> None:
    """Create empty .py files under ``root`` for each rel_path."""
    for rel in rel_paths:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# Exclusion set — the load-bearing invariant
# ---------------------------------------------------------------------------


def test_excluded_dir_names_is_frozenset() -> None:
    """Immutability guard: hooks must not mutate the shared set."""
    assert isinstance(helpers.EXCLUDED_DIR_NAMES, frozenset)


def test_excluded_dir_names_includes_worktrees() -> None:
    """#5394/#5418 regression guard: .worktrees MUST be excluded."""
    assert ".worktrees" in helpers.EXCLUDED_DIR_NAMES


def test_excluded_dir_names_includes_standard_vendored_dirs() -> None:
    """Standard vendored / generated directories stay excluded."""
    for name in {
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".git",
        "dist",
        "build",
    }:
        assert name in helpers.EXCLUDED_DIR_NAMES


# ---------------------------------------------------------------------------
# Full-repo scan mode (no argv)
# ---------------------------------------------------------------------------


def test_full_scan_yields_plain_py_files(tmp_path: Path) -> None:
    _make_tree(tmp_path, ["autobot-backend/module.py", "autobot-slm-backend/x.py"])
    yielded = set(helpers.iter_python_files([], tmp_path))
    assert yielded == {
        tmp_path / "autobot-backend" / "module.py",
        tmp_path / "autobot-slm-backend" / "x.py",
    }


def test_full_scan_excludes_worktrees(tmp_path: Path) -> None:
    """The headline drift-prevention: .worktrees/ is skipped."""
    _make_tree(
        tmp_path,
        [
            "autobot-backend/real.py",
            ".worktrees/issue-1234/autobot-backend/fake.py",
        ],
    )
    yielded = set(helpers.iter_python_files([], tmp_path))
    assert tmp_path / "autobot-backend" / "real.py" in yielded
    assert tmp_path / ".worktrees" / "issue-1234" / "autobot-backend" / "fake.py" not in yielded


def test_full_scan_excludes_standard_vendored(tmp_path: Path) -> None:
    """Each standard excluded dir is honored."""
    _make_tree(
        tmp_path,
        [
            "src/keep.py",
            ".venv/lib/site-packages/skip.py",
            "venv/skip.py",
            "node_modules/pkg/skip.py",
            ".git/hooks/skip.py",
            "dist/skip.py",
            "build/skip.py",
            "src/__pycache__/skip.py",
        ],
    )
    yielded = {p.relative_to(tmp_path).as_posix() for p in helpers.iter_python_files([], tmp_path)}
    assert yielded == {"src/keep.py"}


# ---------------------------------------------------------------------------
# Explicit argv mode (pre-commit / CI)
# ---------------------------------------------------------------------------


def test_argv_mode_yields_absolute_paths(tmp_path: Path) -> None:
    _make_tree(tmp_path, ["app/a.py", "app/b.py"])
    args = [str(tmp_path / "app" / "a.py")]
    yielded = list(helpers.iter_python_files(args, tmp_path))
    assert yielded == [tmp_path / "app" / "a.py"]


def test_argv_mode_resolves_relative_paths(tmp_path: Path) -> None:
    _make_tree(tmp_path, ["app/a.py"])
    yielded = list(helpers.iter_python_files(["app/a.py"], tmp_path))
    assert yielded == [tmp_path / "app" / "a.py"]


def test_argv_mode_filters_non_python_files(tmp_path: Path) -> None:
    _make_tree(tmp_path, ["app/a.py", "app/readme.md"])
    (tmp_path / "app" / "readme.md").write_text("not python", encoding="utf-8")
    yielded = list(helpers.iter_python_files(["app/a.py", "app/readme.md"], tmp_path))
    assert yielded == [tmp_path / "app" / "a.py"]


def test_argv_mode_skips_missing_files(tmp_path: Path) -> None:
    """Non-existent argv entries are silently dropped (pre-commit edge case)."""
    yielded = list(helpers.iter_python_files(["nope.py"], tmp_path))
    assert yielded == []


def test_argv_mode_does_not_apply_excludes(tmp_path: Path) -> None:
    """Explicit argv paths are TRUSTED — even .worktrees/ paths pass through.

    This matches the existing hook behavior: if a developer explicitly
    lints a worktree file, they mean it.
    """
    _make_tree(tmp_path, [".worktrees/issue-1/a.py"])
    args = [str(tmp_path / ".worktrees" / "issue-1" / "a.py")]
    yielded = list(helpers.iter_python_files(args, tmp_path))
    assert yielded == [tmp_path / ".worktrees" / "issue-1" / "a.py"]
