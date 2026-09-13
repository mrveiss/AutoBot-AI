# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

LIB_PATH = Path(__file__).resolve().parent / "_common.sh"


def _test_git_env() -> dict[str, str]:
    """#15246: env for every git subprocess this suite spawns.

    Scrubbed rather than os.environ: the pre-push hook runs this suite with
    GIT_DIR pointing at the worktree it is pushing (every checkout here is
    one), and an unscrubbed `git init`/`git add`/`git commit` in a
    fixture then operates on THAT repository instead of tmp_path's. See
    autobot_shared/paths_test.py and #15246 for the reproduced incident.
    """
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _run_in_subshell(script: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Source _common.sh and run a snippet; capture stdout/stderr/exit."""
    full = f'source "{LIB_PATH}"\n{script}'
    return subprocess.run(["bash", "-c", full], capture_output=True, text=True, cwd=cwd, env=_test_git_env())


def _make_git_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Initialize a git repo at tmp_path with `files` staged."""
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True, env=_test_git_env())
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=tmp_path, check=True, env=_test_git_env())
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True, env=_test_git_env())
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True, env=_test_git_env())
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


def test_get_staged_files_argv_mode_bypasses_git(tmp_path):
    """Positional args bypass `git diff --cached` — the list comes from argv."""
    result = _run_in_subshell(
        'get_staged_files "\\.py$" file1.py file2.py file3.txt',
        cwd=tmp_path,
    )
    assert result.returncode == 0
    # Not a git repo, so a non-empty result can only have come from argv.
    assert result.stdout == "file1.py\nfile2.py\n"


def test_get_staged_files_argv_mode_applies_the_pattern(tmp_path):
    """GH#14034: the argv branch MUST apply $pattern, exactly like the git branch.

    Regression pin. The argv branch used to `printf '%s\\n' "$@"` and return
    without ever running the caller's regex, so every hook's own file-type
    filter was silently bypassed in CI (which always passes argv) while working
    locally under pre-commit (which does not). That handed a .vue file to
    pre-commit-no-direct-redis' Python tokenizer and the resulting
    IndentationError was reported as "1 direct Redis connection(s) found" in a
    file containing no Redis at all.

    This test asserted the OPPOSITE until #14371 — it pinned the bug, so the
    one-line fix had nothing holding it in place.
    """
    result = _run_in_subshell(
        'get_staged_files "\\.py$" file1.txt file2.md',
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == "", "argv branch must drop files that do not match the pattern"


def test_get_staged_files_both_branches_agree(tmp_path):
    """The argv and git branches return the SAME set for the same input (#14034).

    The defect was not "argv is wrong" in isolation — it was that the two
    documented invocation paths disagreed, so a hook was filtered locally and
    unfiltered in CI. Asserting the two agree is what pins that shut; asserting
    either one alone does not.
    """
    tracked = {
        "src/foo.py": "# python",
        "src/bar.vue": "<template/>",
        "docs/readme.md": "# markdown",
    }
    _make_git_repo(tmp_path, tracked)

    from_git = _run_in_subshell('get_staged_files "\\.py$"', cwd=tmp_path)
    argv = " ".join(sorted(tracked))
    from_argv = _run_in_subshell(f'get_staged_files "\\.py$" {argv}', cwd=tmp_path)

    assert from_git.returncode == 0
    assert from_argv.returncode == 0
    assert sorted(from_git.stdout.split()) == sorted(from_argv.stdout.split()) == ["src/foo.py"]


def test_get_staged_files_no_args_outside_a_repo_is_fatal_not_empty(tmp_path):
    """GH#14151: a git failure must NOT be reported as 'nothing staged'.

    The no-argv branch used to pipe `git diff --cached` straight into
    `grep … || true`, and that trailing `|| true` swallowed "grep matched
    nothing" and "git itself failed" identically — both produced empty output.
    Every caller's `[ -z "$files" ] && exit 0` then read a broken git as a clean
    tree.

    This test asserted the swallowing behaviour until #14371 — the third
    assertion in this file found pinning a bug rather than a fix. All three
    were red against the code they cover, on the base branch, unnoticed:
    the Python suite is not a required check here, so a red test in it blocks
    nothing.
    """
    result = _run_in_subshell(
        'get_staged_files "\\.py$"',
        cwd=tmp_path,
    )
    assert result.returncode != 0, "a failed `git diff --cached` was reported as an empty result"
    assert "refusing to report clean" in result.stderr
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
