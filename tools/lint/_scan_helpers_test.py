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
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autobot_shared.paths import scrubbed_git_env  # noqa: E402

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


def _run_git(root: Path, *argv: str) -> None:
    """Run one git command in *root*, refusing to continue if it failed.

    ``env=scrubbed_git_env()`` is not optional here (#15490): pytest inherits
    the ambient hook environment, and an inherited ``GIT_DIR`` makes ``git
    init``/``git add`` operate on the real repository instead of ``tmp_path``.
    """
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", *argv],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=scrubbed_git_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(argv)} failed in {root}: {result.stderr.strip()}")


def _make_tracked_tree(root: Path, tracked: list[str], untracked: tuple[str, ...] = ()) -> None:
    """Build a real git repo at *root* with *tracked* in its index.

    Full-repo mode enumerates ``git ls-files``, so a plain directory is no
    longer a fixture it can read -- and an exclusion assertion is only worth
    something when the excluded file is genuinely tracked, otherwise it
    passes against a listing that never contained the file at all. ``-f``
    defeats any ambient ``core.excludesFile`` that would otherwise skip
    ``venv/`` or ``node_modules/`` and make exactly those assertions vacuous.
    """
    _make_tree(root, tracked)
    _run_git(root, "init", "-q")
    _run_git(root, "add", "-f", "--", *tracked)
    _make_tree(root, list(untracked))


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
    _make_tracked_tree(tmp_path, ["autobot-backend/module.py", "autobot-slm-backend/x.py"])
    yielded = set(helpers.iter_python_files([], tmp_path))
    assert yielded == {
        tmp_path / "autobot-backend" / "module.py",
        tmp_path / "autobot-slm-backend" / "x.py",
    }


def test_full_scan_excludes_worktrees(tmp_path: Path) -> None:
    """The headline drift-prevention: .worktrees/ is skipped.

    Both files are tracked, so the exclusion is proven against a real index
    rather than against an enumeration the worktree file never entered.
    """
    _make_tracked_tree(
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
    """Each standard excluded dir is honored, proven against a real index.

    ``.git/hooks/skip.py`` is created but deliberately NOT tracked: git
    refuses to add a path inside its own directory, so a tracked
    enumeration can never surface one. It stays on disk so this still pins
    that a stray file under ``.git`` is not yielded.
    """
    _make_tracked_tree(
        tmp_path,
        [
            "src/keep.py",
            ".venv/lib/site-packages/skip.py",
            "venv/skip.py",
            "node_modules/pkg/skip.py",
            "dist/skip.py",
            "build/skip.py",
            "src/__pycache__/skip.py",
        ],
        untracked=(".git/hooks/skip.py",),
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


# ---------------------------------------------------------------------------
# logical_lines — shell continuation folding (#15938, #15961)
# ---------------------------------------------------------------------------


def test_logical_lines_with_no_continuation_is_one_entry_per_physical_line() -> None:
    assert helpers.logical_lines("git status\ngit log") == [(1, "git status"), (2, "git log")]


def test_logical_lines_folds_a_two_line_continuation() -> None:
    """The shape a long invocation is actually written in (#15961).

    Neutral tokens on purpose: the guards that call this helper scan every
    tracked file, this one included, so a real offending spelling would trip
    them. The guards' own test files carry the real spellings as fixtures.
    """
    joined = helpers.logical_lines("some-tool subcommand \\\n  --dangerous-flag /tmp/x")
    assert len(joined) == 1
    number, line = joined[0]
    assert number == 1
    assert "some-tool subcommand" in line and "--dangerous-flag /tmp/x" in line


def test_logical_lines_folds_a_three_line_continuation() -> None:
    joined = helpers.logical_lines("some-tool \\\n  -o \\\n  option=/tmp/x run")
    assert len(joined) == 1
    number, line = joined[0]
    assert number == 1
    assert "-o" in line
    assert "option=/tmp/x" in line
    assert "run" in line


def test_logical_lines_does_not_fold_a_mid_line_backslash() -> None:
    """A backslash is only a continuation as the LAST character of the line."""
    assert helpers.logical_lines("echo a\\b\ngit status") == [
        (1, "echo a\\b"),
        (2, "git status"),
    ]


def test_logical_lines_reports_the_first_physical_line_of_each_fold() -> None:
    """Numbering follows the fold, not the physical line count.

    Line 1 stands alone at 1; lines 2-3 fold into one logical line reported at
    the FIRST of the two (2), not the last; line 4 stands alone at 4 -- the
    gap where line 3 would have been is the proof the number is not just an
    incrementing counter over the output list.
    """
    joined = helpers.logical_lines("one\ntwo \\\n  three\nfour")
    assert joined[0] == (1, "one")
    assert joined[1][0] == 2
    assert joined[2] == (4, "four")
