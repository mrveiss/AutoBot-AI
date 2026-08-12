# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-gitignore-shadow (#14137).

The other half of how the venv symlink got in: `.gitignore` carried
`venv/` with a trailing slash (directory-only), so a `venv` *symlink* was
never ignored and `git add -A` swept it in. This hook independently
confirms the OUTCOME .gitignore's virtualenv section is meant to
guarantee — no tracked path is named after one of its entries — rather
than re-deriving gitignore's own pattern-matching rules.

Every fixture writes its own throwaway `.gitignore` in a tmp_path git repo,
so a change to the real repo's virtualenv section can't accidentally make
these tests pass or fail for the wrong reason.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-gitignore-shadow"

_SECTION = (
    "# === PYTHON VIRTUAL ENVIRONMENT ===\n"
    "venv\n"
    "venv/\n"
    "venvs\n"
    "venvs/\n"
    "bin/\n"
    "lib/\n"
    "!scripts/lib/\n"
    "lib64/\n"
    "include/\n"
    "share/\n"
    "pyvenv.cfg\n"
    "\n"
    "# === NODE.JS AND NPM ===\n"
    "node_modules/\n"
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path, gitignore: str = _SECTION) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / ".gitignore").write_text(gitignore, encoding="utf-8")
    return repo


def _track(repo: Path, path: str, content: str = "x\n") -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(repo, "add", "-f", path)


def _run_hook(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)


# === Ordinary tracked tree — must not be blocked ===


def test_clean_tree_with_no_shadowing_paths_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _track(repo, "app/main.py")
    _track(repo, ".gitignore", _SECTION)
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


# === A tracked path shadowing a bare ignore name is rejected ===


def test_top_level_venv_directory_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _track(repo, "venv/pyvenv.cfg")
    _track(repo, ".gitignore", _SECTION)
    result = _run_hook(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "venv" in result.stdout


def test_nested_directory_named_venv_is_rejected(tmp_path: Path) -> None:
    """A bare gitignore entry (no slash) matches at any depth — this hook
    must mirror that, not just check the top level."""
    repo = _init_repo(tmp_path)
    _track(repo, "some/deep/venv/site-packages/pkg/__init__.py")
    _track(repo, ".gitignore", _SECTION)
    result = _run_hook(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "some/deep/venv/site-packages/pkg/__init__.py" in result.stdout


def test_bare_pyvenv_cfg_file_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _track(repo, "pyvenv.cfg")
    _track(repo, ".gitignore", _SECTION)
    result = _run_hook(repo)
    assert result.returncode == 1


# === The allowlist (a `!` negation) works, and does not swallow everything ===


def test_negated_path_is_allowed(tmp_path: Path) -> None:
    """scripts/lib/ is explicitly negated — must not be flagged."""
    repo = _init_repo(tmp_path)
    _track(repo, "scripts/lib/helper.sh")
    _track(repo, ".gitignore", _SECTION)
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_negation_does_not_exempt_a_different_lib_path(tmp_path: Path) -> None:
    """The allowlist must be a narrow prefix match, not a name-wide pass —
    a `lib/` outside scripts/ is still a violation."""
    repo = _init_repo(tmp_path)
    _track(repo, "other/lib/helper.sh")
    _track(repo, ".gitignore", _SECTION)
    result = _run_hook(repo)
    assert result.returncode == 1, "negation for scripts/lib/ leaked to an unrelated lib/ path"
    assert "other/lib/helper.sh" in result.stdout


def test_negation_prefix_respects_a_slash_boundary(tmp_path: Path) -> None:
    """`scripts/lib/` is negated; `scripts/lib-extra/` is a different
    directory that merely shares the string prefix "scripts/lib". If the
    negation check used a bare string-prefix test instead of a '/'-bounded
    one, this path would be wrongly exempted (exit 0) via the "lib" segment
    the negation was never meant to cover."""
    repo = _init_repo(tmp_path)
    _track(repo, "scripts/lib-extra/lib/mod.py")
    _track(repo, ".gitignore", _SECTION)
    result = _run_hook(repo)
    assert result.returncode == 1, "negation for scripts/lib/ leaked past its own '/' boundary"
    assert "scripts/lib-extra/lib/mod.py" in result.stdout


# === Fail closed if the section marker itself goes missing ===


def test_missing_section_marker_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, gitignore="node_modules/\n*.pyc\n")
    result = _run_hook(repo)
    assert result.returncode != 0
    assert "marker not found" in result.stdout + result.stderr


def test_missing_gitignore_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / ".gitignore").unlink()
    result = _run_hook(repo)
    assert result.returncode != 0


class TestTheGuardFailsClosedWhenItCannotRun:
    """Companion to the same class in the symlink hook's tests.

    This hook already failed closed for a missing marker and for a virtualenv
    section parsing to zero names — both deliberately tested. The two paths
    nobody tested were a missing `lib/_common.sh` and `git ls-files` erroring,
    and those reported clean (#14150 review).

    The pattern is worth naming: the failure modes that were considered were
    handled; the ones that were not considered were not. Testing what you
    already thought about proves the least.
    """

    def test_a_missing_common_lib_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)

        isolated = tmp_path / "isolated"
        isolated.mkdir()
        hook_copy = isolated / HOOK_PATH.name
        hook_copy.write_bytes(HOOK_PATH.read_bytes())
        hook_copy.chmod(0o755)

        result = subprocess.run([str(hook_copy)], cwd=repo, capture_output=True, text=True)

        assert result.returncode != 0, "the hook reported clean without its dependency"

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = _run_hook(repo)

        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
