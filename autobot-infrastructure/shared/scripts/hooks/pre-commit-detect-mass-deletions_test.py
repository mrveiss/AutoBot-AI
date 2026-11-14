# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-detect-mass-deletions (#4111, GH#14151 fail-closed
guard).

Issue #14151: see pre-commit-no-direct-redis_test.py's module docstring for
the shared background. This hook doesn't use get_staged_files() at all — it
calls `git diff --cached --diff-filter=D` directly into a bare top-level
assignment, so `set -e` alone (no lib/_common.sh change needed) is enough to
make a git failure abort instead of silently reading as "0 deletions,
allow". Its opening also references an unbound color variable only inside
the >50 violation branch, under `set -u`, which independently closed the
"missing lib/_common.sh" case pre-fix — only the git-failure path is the
genuine, newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from autobot_shared.isolated_git import isolated_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-detect-mass-deletions"


DELETION_THRESHOLD = 50


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=isolated_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _commit_and_stage_deletion_of(repo: Path, count: int) -> None:
    for i in range(count):
        (repo / f"f{i}.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed many files")
    for i in range(count):
        (repo / f"f{i}.txt").unlink()
    _git(repo, "add", "-A")


def test_allows_deletions_at_or_below_threshold(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_and_stage_deletion_of(repo, DELETION_THRESHOLD)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=isolated_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


def test_blocks_mass_deletion_above_threshold(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_and_stage_deletion_of(repo, DELETION_THRESHOLD + 10)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=isolated_git_env())
    assert result.returncode != 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "0 files deleted" — reproduced with a genuine mass-deletion staged.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit_and_stage_deletion_of(repo, DELETION_THRESHOLD + 10)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(
            ["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=isolated_git_env()
        )
        assert result.returncode != 0, "a git failure was indistinguishable from '0 deletions'"


class TestMergeAware:
    """A merge bringing in deletions main already made is not an accident (#18238).

    Catching an old branch up with main stages every file main removed since the
    branch was cut; those paths are absent from origin/main, so they are not counted.
    The exemption is keyed on origin/main, never on MERGE_HEAD: merging a branch that
    itself deletes files leaves them on origin/main, so they still count (#19166 review).
    """

    def _repo_with_main(self, tmp_path: Path, files: int) -> Path:
        repo = _init_repo(tmp_path)
        _git(repo, "checkout", "-q", "-b", "main")
        for i in range(files):
            (repo / f"f{i}.txt").write_text("x\n", encoding="utf-8")
        (repo / "keep.txt").write_text("k\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
        return repo

    def _commit(self, repo: Path, msg: str) -> None:
        _git(repo, "add", "-A")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)

    def _publish_main(self, repo: Path) -> None:
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")

    def _catch_up(self, tmp_path: Path, count: int, publish: bool = True) -> Path:
        """An old branch merges a main that removed `count` files since it was cut."""
        repo = self._repo_with_main(tmp_path, count)
        _git(repo, "checkout", "-q", "-b", "old-branch")
        (repo / "branch-work.txt").write_text("b\n", encoding="utf-8")
        self._commit(repo, "branch work")
        _git(repo, "checkout", "-q", "main")
        for i in range(count):
            (repo / f"f{i}.txt").unlink()
        self._commit(repo, "main removes files")
        if publish:
            self._publish_main(repo)
        _git(repo, "checkout", "-q", "old-branch")
        _git(repo, "merge", "--no-commit", "--no-ff", "main")
        return repo

    def _run(self, repo: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=isolated_git_env())

    def test_a_catch_up_merge_of_deletions_main_already_made_is_allowed(self, tmp_path: Path) -> None:
        repo = self._catch_up(tmp_path, DELETION_THRESHOLD + 10)
        staged = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=D").stdout.split()
        assert len(staged) == DELETION_THRESHOLD + 10  # the scenario really stages a mass deletion
        result = self._run(repo)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_contrast_merging_a_branch_that_deletes_files_still_on_main_is_blocked(self, tmp_path: Path) -> None:
        # The case keyed-on-MERGE_HEAD would miss: a PR head deleting files, merged into main.
        repo = self._repo_with_main(tmp_path, DELETION_THRESHOLD + 10)
        self._publish_main(repo)
        _git(repo, "checkout", "-q", "-b", "deleter")
        for i in range(DELETION_THRESHOLD + 10):
            (repo / f"f{i}.txt").unlink()
        self._commit(repo, "branch deletes files")
        _git(repo, "checkout", "-q", "main")
        (repo / "main-work.txt").write_text("m\n", encoding="utf-8")
        self._commit(repo, "main moves on")
        self._publish_main(repo)
        _git(repo, "merge", "--no-commit", "--no-ff", "deleter")
        result = self._run(repo)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "f0.txt" in result.stdout

    def test_contrast_a_stash_style_drop_during_a_catch_up_merge_is_blocked(self, tmp_path: Path) -> None:
        repo = self._catch_up(tmp_path, 5)
        # mid-merge, an accident drops many files main still has
        for i in range(DELETION_THRESHOLD + 10):
            (repo / f"extra{i}.txt").write_text("e\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "finish merge")
        _git(repo, "checkout", "-q", "main")
        _git(repo, "merge", "-q", "old-branch")
        # advance main independently, else main is an ancestor and the merge is a no-op
        (repo / "main-late.txt").write_text("m\n", encoding="utf-8")
        self._commit(repo, "main moves on")
        self._publish_main(repo)
        _git(repo, "checkout", "-q", "old-branch")
        (repo / "late.txt").write_text("l\n", encoding="utf-8")
        self._commit(repo, "diverge")
        _git(repo, "merge", "--no-commit", "--no-ff", "main")
        assert _git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0  # really mid-merge
        for i in range(DELETION_THRESHOLD + 10):
            (repo / f"extra{i}.txt").unlink()
        _git(repo, "add", "-A")
        result = self._run(repo)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "extra0.txt" in result.stdout

    def test_contrast_deleting_files_the_branch_added_during_a_catch_up_merge_is_blocked(self, tmp_path: Path) -> None:
        # Branch-only files are absent from origin/main but never existed at the merge base.
        count = DELETION_THRESHOLD + 10
        repo = self._repo_with_main(tmp_path, 3)
        _git(repo, "checkout", "-q", "-b", "old-branch")
        for i in range(count):
            (repo / f"branch-only{i}.txt").write_text("b\n", encoding="utf-8")
        self._commit(repo, "branch adds files")
        _git(repo, "checkout", "-q", "main")
        (repo / "main-work.txt").write_text("m\n", encoding="utf-8")
        self._commit(repo, "main moves on")
        self._publish_main(repo)
        _git(repo, "checkout", "-q", "old-branch")
        _git(repo, "merge", "--no-commit", "--no-ff", "main")
        assert _git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0
        for i in range(count):
            (repo / f"branch-only{i}.txt").unlink()
        _git(repo, "add", "-A")
        result = self._run(repo)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "branch-only0.txt" in result.stdout

    def test_fails_closed_without_origin_main_every_deletion_counts(self, tmp_path: Path) -> None:
        repo = self._catch_up(tmp_path, DELETION_THRESHOLD + 10, publish=False)
        result = self._run(repo)
        assert result.returncode != 0, result.stdout + result.stderr


class TestPathnamesSurviveIntact:
    """Paths git would C-quote in line output (tab, newline, quote, non-ASCII) are
    read NUL-delimited, so the origin/main membership check sees the real path
    (#19191 review)."""

    @staticmethod
    def _awkward(i: int) -> str:
        return f'q"\t\u00e9\n{i}.txt'

    def _seed(self, tmp_path: Path, count: int) -> Path:
        repo = _init_repo(tmp_path)
        _git(repo, "checkout", "-q", "-b", "main")
        for i in range(count):
            (repo / self._awkward(i)).write_text("x\n", encoding="utf-8")
        (repo / "keep.txt").write_text("k\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
        return repo

    def _commit(self, repo: Path, msg: str) -> None:
        _git(repo, "add", "-A")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)

    def _run(self, repo: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=isolated_git_env())

    def test_a_catch_up_merge_of_quoted_paths_main_already_removed_is_allowed(self, tmp_path: Path) -> None:
        count = DELETION_THRESHOLD + 10
        repo = self._seed(tmp_path, count)
        _git(repo, "checkout", "-q", "-b", "old-branch")
        (repo / "branch-work.txt").write_text("b\n", encoding="utf-8")
        self._commit(repo, "branch work")
        _git(repo, "checkout", "-q", "main")
        for i in range(count):
            (repo / self._awkward(i)).unlink()
        self._commit(repo, "main removes files")
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        _git(repo, "checkout", "-q", "old-branch")
        _git(repo, "merge", "--no-commit", "--no-ff", "main")
        quoted = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=D").stdout.splitlines()
        assert all(line.startswith('"') for line in quoted)  # git really quotes these paths
        result = self._run(repo)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_contrast_merging_a_branch_deleting_quoted_paths_still_on_main_is_blocked(self, tmp_path: Path) -> None:
        count = DELETION_THRESHOLD + 10
        repo = self._seed(tmp_path, count)
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        _git(repo, "checkout", "-q", "-b", "deleter")
        for i in range(count):
            (repo / self._awkward(i)).unlink()
        self._commit(repo, "branch deletes files")
        _git(repo, "checkout", "-q", "main")
        (repo / "main-work.txt").write_text("m\n", encoding="utf-8")
        self._commit(repo, "main moves on")
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        _git(repo, "merge", "--no-commit", "--no-ff", "deleter")
        result = self._run(repo)
        assert result.returncode != 0, result.stdout + result.stderr
        assert f"Staged deletions: \x1b[1m{count}\x1b[0m files" in result.stdout


class TestGitlinkMembership:
    """Membership on origin/main is read from its tree listing, never from object
    availability: a gitlink whose commit is absent locally is still an entry on main,
    so deleting it still counts (#19191 review)."""

    def test_deleting_gitlinks_still_on_main_whose_commits_are_absent_is_blocked(self, tmp_path: Path) -> None:
        count = DELETION_THRESHOLD + 10
        repo = _init_repo(tmp_path)
        _git(repo, "checkout", "-q", "-b", "main")
        (repo / "keep.txt").write_text("k\n", encoding="utf-8")
        _git(repo, "add", "keep.txt")
        for i in range(count):
            _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{i + 1:040x},sub/m{i}")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed gitlinks")
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        absent = subprocess.run(["git", "cat-file", "-e", "main:sub/m0"], cwd=repo, env=isolated_git_env(), check=False)
        assert absent.returncode != 0  # the gitlink's commit object is not in this repo
        _git(repo, "checkout", "-q", "-b", "deleter")
        for i in range(count):
            _git(repo, "rm", "-q", "--cached", f"sub/m{i}")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "branch deletes gitlinks")
        _git(repo, "checkout", "-q", "main")
        (repo / "main-work.txt").write_text("m\n", encoding="utf-8")
        _git(repo, "add", "main-work.txt")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "main moves on")
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        _git(repo, "merge", "--no-commit", "--no-ff", "deleter")
        _git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD")  # raises unless mid-merge
        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=isolated_git_env())
        assert result.returncode != 0, result.stdout + result.stderr
        assert f"Staged deletions: \x1b[1m{count}\x1b[0m files" in result.stdout
