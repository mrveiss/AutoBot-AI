# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/verify-done.sh (#13879).

Every case here is a false "has landed — remove it" verdict from the removed
first implementation (preserved at ff511b168). That verdict is a delete
instruction, so a wrong one costs work: a one-character typo in the base ref
reported 17 worktrees as landed where 3 were.

The governing property: a check that cannot run is a FAILURE, never a verdict.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "verify-done.sh"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    )


def _commit(repo: Path, name: str, body: str, subject: str) -> None:
    (repo / name).write_text(body, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", subject)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A repo with a `base` branch and one commit, plus a worktrees dir."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "base")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    _commit(r, "seed.txt", "seed\n", "chore(seed): base (#1)")
    return r


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--leftovers-only", *args],
        cwd=repo, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(repo)},
    )


def add_worktree(repo: Path, name: str, commits: list[tuple[str, str]]) -> Path:
    """Create a worktree on its own branch with the given (file, subject) commits."""
    wt = repo / ".worktrees" / name
    _git(repo, "worktree", "add", "-q", str(wt), "-b", name, "base")
    for fname, subject in commits:
        _commit(wt, fname, f"content of {fname}\n", subject)
    return wt


@pytest.mark.skipif(not SCRIPT.exists(), reason="verify-done.sh not present")
class TestNeverDeletesUnlandedWork:
    def test_unresolvable_base_fails_and_names_nothing_landed(self, repo: Path) -> None:
        """Trigger (a): a typo'd base made EVERY worktree look landed."""
        add_worktree(repo, "wt-a", [("a.txt", "feat(a): thing (#2)")])
        add_worktree(repo, "wt-b", [("b.txt", "feat(b): thing (#3)")])
        res = run(repo, "--base", "no-such-ref")
        assert res.returncode != 0, res.stdout
        assert "has landed" not in res.stdout
        assert "does not resolve" in (res.stdout + res.stderr).lower()

    def test_zero_commit_worktree_is_not_landed(self, repo: Path) -> None:
        """Trigger (b): a session that just started looked finished."""
        add_worktree(repo, "wt-fresh", [])
        res = run(repo, "--base", "base")
        assert "has landed" not in res.stdout, res.stdout
        assert "no commits" in res.stdout.lower()

    def test_tip_subject_collision_does_not_mark_unlanded_work_landed(self, repo: Path) -> None:
        """Trigger (c): the tip's subject also existed in base, so the OR fired."""
        wt = add_worktree(
            repo, "wt-collide",
            [
                ("real1.txt", "fix(core): genuine unlanded work (#4)"),
                ("real2.txt", "fix(core): more unlanded work (#5)"),
                ("chg.txt", "docs: update the changelog (#6)"),
            ],
        )
        # The SAME subject lands on base via a different patch.
        _commit(repo, "other.txt", "unrelated\n", "docs: update the changelog (#6)")
        res = run(repo, "--base", "base")
        assert "has landed" not in res.stdout, (
            "three unlanded commits must never be reported landed because the "
            f"tip subject collides\n{res.stdout}"
        )
        assert wt.exists()

    def test_genuinely_landed_worktree_is_reported(self, repo: Path) -> None:
        """The guard must stay useful — over-correcting to 'never landed' is a bug too.

        Models a SQUASH merge, which is how this repo lands work: base gains a
        commit with the same diff but a different sha, so the branch stays
        ahead while every patch-id matches. A plain cherry-pick would
        fast-forward base and leave the branch 0 ahead, which is genuinely
        ambiguous with a freshly created worktree — see the test below.
        """
        add_worktree(repo, "wt-done", [("done.txt", "fix(x): landed work (#7)")])
        sha = _git(repo, "rev-parse", "wt-done").stdout.strip()
        _git(repo, "cherry-pick", "--no-commit", sha)
        _git(repo, "commit", "-q", "-m", "fix(x): landed work (#7) (squashed)")
        res = run(repo, "--base", "base")
        assert "wt-done" in res.stdout
        assert "has landed" in res.stdout, res.stdout

    def test_fast_forwarded_branch_is_kept_not_deleted(self, repo: Path) -> None:
        """`ahead == 0` is ambiguous, so the conservative answer is KEEP.

        A branch whose commits base already contains looks identical to a
        worktree created seconds ago that has done nothing yet. Keeping a
        removable worktree costs disk; deleting an active one costs work.
        """
        add_worktree(repo, "wt-ff", [("ff.txt", "fix(y): work (#8)")])
        sha = _git(repo, "rev-parse", "wt-ff").stdout.strip()
        _git(repo, "cherry-pick", sha)  # fast-forwards base onto that commit
        res = run(repo, "--base", "base")
        assert "has landed" not in res.stdout, res.stdout
        assert res.returncode == 0


@pytest.mark.skipif(not SCRIPT.exists(), reason="verify-done.sh not present")
class TestFailsRatherThanGuesses:
    def test_exit_code_is_nonzero_when_anything_is_unverifiable(self, repo: Path) -> None:
        res = run(repo, "--base", "definitely-not-a-ref")
        assert res.returncode != 0

    def test_clean_repo_with_no_worktrees_passes(self, repo: Path) -> None:
        res = run(repo, "--base", "base")
        assert res.returncode == 0, res.stdout
