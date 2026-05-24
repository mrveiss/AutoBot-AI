# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for lib/_common.sh (Issue #7193).

Locks down behavior of the shared hook library before #7185 fans out
the conversion to all 13 hooks. Once 13 hooks depend on _common.sh, a
subtle bug in get_staged_files would break all of them at once —
unit tests caught here keep blast radius small.

Each test sources _common.sh in a subshell, exercises one function,
and asserts on stdout/exit code.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LIB_PATH = Path(__file__).resolve().parent / "_common.sh"


def _run_in_subshell(script: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Source _common.sh and run a snippet; capture stdout/stderr/exit."""
    full = f'source "{LIB_PATH}"\n{script}'
    return subprocess.run(
        ["bash", "-c", full],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _make_git_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Initialize a git repo at tmp_path with `files` staged."""
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)
    return tmp_path


# === Color codes ===


def test_color_codes_exported():
    """RED/GREEN/YELLOW/CYAN/BOLD/NC are defined and ANSI-escape strings."""
    result = _run_in_subshell('printf "%s|%s|%s|%s|%s|%s" "$RED" "$YELLOW" "$GREEN" "$CYAN" "$BOLD" "$NC"')
    assert result.returncode == 0
    parts = result.stdout.split("|")
    assert len(parts) == 6
    # Each should be an ANSI escape sequence (starts with \033[ or actual ESC)
    for p in parts:
        assert "[" in p, f"expected ANSI escape, got {p!r}"


# === get_staged_files: argv mode ===


def test_get_staged_files_argv_mode_passes_through(tmp_path):
    """When positional args are provided, they bypass git diff."""
    result = _run_in_subshell(
        'get_staged_files "ignored_pattern" file1.py file2.py file3.txt',
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == "file1.py\nfile2.py\nfile3.txt\n"


def test_get_staged_files_argv_mode_pattern_ignored(tmp_path):
    """Argv mode does NOT filter by pattern — caller is expected to pre-filter.

    This matches the #6785 generic-wrapper convention: CI passes the exact
    file list it wants checked.
    """
    result = _run_in_subshell(
        'get_staged_files "\\.py$" file1.txt file2.md',
        cwd=tmp_path,
    )
    assert result.returncode == 0
    # file1.txt and file2.md are returned even though they don't match \.py$
    assert result.stdout == "file1.txt\nfile2.md\n"


def test_get_staged_files_argv_mode_no_args(tmp_path):
    """No positional args + no git → falls through to git path; in non-git tmpdir, returns empty."""
    result = _run_in_subshell(
        'get_staged_files "\\.py$"',
        cwd=tmp_path,
    )
    # In a non-git dir, `git diff --cached` errors; we use `|| true` so exit is still 0
    assert result.returncode == 0
    assert result.stdout == ""


# === get_staged_files: git mode ===


def test_get_staged_files_git_mode_filters_by_pattern(tmp_path):
    """When no argv args, reads staged files and filters by pattern."""
    _make_git_repo(
        tmp_path,
        {
            "src/foo.py": "# python",
            "src/bar.py": "# python",
            "docs/readme.md": "# markdown",
            "config.yml": "key: value",
        },
    )
    result = _run_in_subshell(
        'get_staged_files "\\.py$"',
        cwd=tmp_path,
    )
    assert result.returncode == 0
    # Only .py files match
    lines = sorted(result.stdout.strip().split("\n"))
    assert lines == ["src/bar.py", "src/foo.py"]


def test_get_staged_files_git_mode_no_match(tmp_path):
    """Pattern with zero matches returns empty stdout, exit 0."""
    _make_git_repo(
        tmp_path,
        {
            "src/foo.py": "# python",
            "docs/readme.md": "# markdown",
        },
    )
    result = _run_in_subshell(
        'get_staged_files "\\.tsx$"',
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_get_staged_files_git_mode_workflow_pattern(tmp_path):
    """Realistic pattern from pre-commit-no-tag-pinned-action."""
    _make_git_repo(
        tmp_path,
        {
            ".github/workflows/ci.yml": "name: CI",
            ".github/actions/setup/action.yml": "name: setup",
            ".github/dependabot.yml": "version: 2",
            "src/main.py": "# code",
        },
    )
    result = _run_in_subshell(
        "get_staged_files '^\\.github/(workflows|actions)/.*\\.ya?ml$'",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    lines = sorted(result.stdout.strip().split("\n"))
    assert lines == [".github/actions/setup/action.yml", ".github/workflows/ci.yml"]
    # dependabot.yml at .github/ root is correctly excluded


# === Idempotent sourcing ===


def test_idempotent_sourcing(tmp_path):
    """Sourcing _common.sh twice doesn't re-define / break anything."""
    result = _run_in_subshell(
        f'source "{LIB_PATH}"\n'  # second source
        'echo "$_AUTOBOT_HOOK_COMMON_LOADED"\n'
        'printf "%s" "$RED"',
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "1" in result.stdout  # guard variable set
    assert "[" in result.stdout  # color still defined


def test_guard_variable_set():
    """First source sets _AUTOBOT_HOOK_COMMON_LOADED=1."""
    result = _run_in_subshell('echo "$_AUTOBOT_HOOK_COMMON_LOADED"')
    assert result.returncode == 0
    assert result.stdout.strip() == "1"
