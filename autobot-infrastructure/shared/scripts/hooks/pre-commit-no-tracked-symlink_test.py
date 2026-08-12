# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-tracked-symlink (#14137).

The defect this hook guards against is invisible to a content diff — a
committed symlink and a one-line text file look identical in `git show`.
Only the INDEX MODE (`git ls-files -s` reporting `120000`) reveals it, so
every fixture here stages entries via `git update-index --add --cacheinfo
120000,<blob-sha>,<path>` rather than actually creating filesystem symlinks:
that is also what makes it possible to construct this on ANY machine,
including one where `core.symlinks=true` and a real symlink would just work.

Nothing here commits a symlink into the AutoBot-AI repository itself; every
fixture lives in a throwaway `tmp_path` git repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-tracked-symlink"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "core.symlinks", "false")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
    return repo


def _stage_symlink(repo: Path, path: str, target: str) -> None:
    """Stage a tracked mode-120000 entry with the given TARGET, without ever
    creating a real filesystem symlink (so this works under core.symlinks
    of either setting, and on any OS)."""
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input=target,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},{path}")


def _stage_file(repo: Path, path: str, content: str = "hello\n") -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(repo, "add", path)


def _run_hook(repo: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(HOOK_PATH), *argv], cwd=repo, capture_output=True, text=True)


# === Ordinary files must not be blocked ===


def test_ordinary_staged_file_is_accepted(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_file(repo, "app.py", "x = 1\n")
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_staged_files_exits_zero(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = _run_hook(repo)
    assert result.returncode == 0


# === The destructive class: mode 120000 pointing inside the tree ===


def test_symlink_inside_tree_self_referential_absolute_target_rejected(tmp_path: Path) -> None:
    """The exact #14137 shape: an absolute target equal to the repo's own root + path."""
    repo = _init_repo(tmp_path)
    _stage_symlink(repo, "venv", f"{repo}/venv")
    result = _run_hook(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "venv" in result.stdout
    assert "INSIDE" in result.stdout or "targets INSIDE" in result.stdout


def test_symlink_inside_tree_relative_traversal_rejected(tmp_path: Path) -> None:
    """The exact #14149 shape: a relative target whose '..' climbs land back inside the repo."""
    repo = _init_repo(tmp_path)
    _stage_symlink(
        repo,
        "autobot-slm-backend/ansible/tests/inventory/group_vars/all.yml",
        "../../../inventory/group_vars/all.yml",
    )
    result = _run_hook(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "targets INSIDE" in result.stdout


def test_symlink_inside_tree_via_short_relative_target_rejected(tmp_path: Path) -> None:
    """A relative target that never escapes the containing directory at all."""
    repo = _init_repo(tmp_path)
    (repo / "sub").mkdir()
    _stage_symlink(repo, "sub/link", "real.txt")
    result = _run_hook(repo)
    assert result.returncode == 1
    assert "targets INSIDE" in result.stdout


# === Outside-the-tree targets: still rejected, distinct message ===


def test_symlink_outside_tree_absolute_target_rejected_with_distinct_message(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_symlink(repo, "outlink", "/etc/passwd")
    result = _run_hook(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "targets OUTSIDE" in result.stdout
    # The two classes must not be conflated in the operator-facing message.
    assert "targets INSIDE" not in result.stdout


def test_symlink_outside_tree_relative_traversal_rejected(tmp_path: Path) -> None:
    """Enough '..' to climb above the repo root entirely."""
    repo = _init_repo(tmp_path)
    (repo / "sub").mkdir()
    _stage_symlink(repo, "sub/link", "../../outside.txt")
    result = _run_hook(repo)
    assert result.returncode == 1
    assert "targets OUTSIDE" in result.stdout


# === Deletion is the fix direction, never a violation ===


def test_deleting_a_tracked_symlink_is_not_a_violation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_symlink(repo, "venv", f"{repo}/venv")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "add bad symlink")
    _git(repo, "rm", "-q", "venv")
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


# === Changed-files scoping: a PRE-EXISTING violation must not block
#     unrelated commits (#14149 is exactly this shape against the real repo) ===


def test_pre_existing_symlink_untouched_by_this_commit_does_not_block(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_symlink(repo, "preexisting", "/etc/hosts")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "pre-existing violation, already landed")

    _stage_file(repo, "unrelated.py", "x = 1\n")
    result = _run_hook(repo)

    assert result.returncode == 0, f"pre-existing violation blocked an unrelated commit:\n{result.stdout}"


def test_a_newly_staged_symlink_alongside_unrelated_changes_still_fails(tmp_path: Path) -> None:
    """The scoping change must not become an off switch."""
    repo = _init_repo(tmp_path)
    _stage_file(repo, "unrelated.py", "x = 1\n")
    _stage_symlink(repo, "venv", f"{repo}/venv")

    result = _run_hook(repo)

    assert result.returncode == 1


# === CI / argv mode: explicit file list (the calling workflow computes the
#     PR's changed-file set and passes it positionally) ===


def test_argv_mode_flags_an_explicitly_passed_symlink_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_symlink(repo, "venv", f"{repo}/venv")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "landed symlink")

    result = _run_hook(repo, "venv")

    assert result.returncode == 1, result.stdout + result.stderr


def test_argv_mode_ignores_paths_not_passed(tmp_path: Path) -> None:
    """Argv mode scopes to exactly what the caller passed — #14149's path,
    landed but not in THIS argv list, must not surface."""
    repo = _init_repo(tmp_path)
    _stage_symlink(repo, "preexisting", "/etc/hosts")
    _stage_file(repo, "other.py", "x = 1\n")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "mixed commit")

    result = _run_hook(repo, "other.py")

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script not found")
def test_hook_script_exists_and_is_executable() -> None:
    """core.fileMode=false in this repo means `chmod +x` never reaches the
    index (#14051 topic, same gotcha) — a hook committed as 100644 dies with
    exit 126 in CI. This guards the artifact, not the logic."""
    import os

    assert os.access(HOOK_PATH, os.X_OK), f"{HOOK_PATH} is not executable on disk"


class TestTheGuardFailsClosedWhenItCannotRun:
    """Review of #14150 found both hooks failing OPEN — reporting clean while a
    genuinely staged symlink was present.

    `set -uo pipefail` (no `-e`) plus an unguarded `source` meant a missing
    dependency degraded to an empty result, which the scripts read as "nothing
    to check" and exited 0. The same shape via `git` erroring: `check_file`'s
    `[ -n "$ls_line" ] || return 0` treats "git failed" and "no index entry"
    identically.

    That is #14051's defect verbatim, in the hook built to stop that class. A
    guard reporting green because it never ran is worse than no guard — it
    manufactures confidence.

    The marker-missing and empty-NAMES paths were already tested and already
    failed closed. These two were not tested, and did not.
    """

    def test_a_missing_common_lib_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage_symlink(repo, "venv", str(repo))

        # A copy of the hook with no `lib/` beside it — the dependency is gone.
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        hook_copy = isolated / HOOK_PATH.name
        hook_copy.write_bytes(HOOK_PATH.read_bytes())
        hook_copy.chmod(0o755)

        result = subprocess.run([str(hook_copy)], cwd=repo, capture_output=True, text=True)

        assert result.returncode != 0, "the hook reported clean with a staged symlink and no dependency"

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage_symlink(repo, "venv", str(repo))
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = _run_hook(repo, "venv")

        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
