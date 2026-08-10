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


def run(repo: Path, *args: str, merged_pr: str | None = None) -> subprocess.CompletedProcess:
    """Run the audit.

    ``merged_pr`` installs a ``gh`` stub reporting that PR number as merged.
    Without it the real ``gh`` finds no GitHub remote for a tmp repo, so every
    landed case exits early through "gh could not be queried — keep" and the
    ENTIRE delete path — the merged-PR gate, the dirty gate, the ignored-file
    listing and the instruction itself — is unreachable by any test. That gap
    is how the tag-shadowing and ignored-file fixes originally shipped with no
    coverage at all.
    """
    env = {"PATH": "/usr/bin:/bin", "HOME": str(repo)}
    if merged_pr is not None:
        bindir = repo / ".stub-bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "gh"
        stub.write_text(f'#!/bin/sh\necho "{merged_pr}"\n', encoding="utf-8")
        stub.chmod(0o755)
        env["PATH"] = f"{bindir}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), "--leftovers-only", *args],
        cwd=repo, capture_output=True, text=True, env=env,
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
        # The patch-id signal must fire...
        assert "landed by patch-id" in res.stdout or "has landed" in res.stdout, res.stdout
        # ...but on its own it must NOT authorize deletion. There is no merged
        # PR for this throwaway branch, so the second signal is absent and the
        # verdict must stay on the safe side.
        assert "remove it" not in res.stdout, (
            "a single git heuristic must never produce a delete instruction\n" + res.stdout
        )

    def test_claimed_worktree_with_only_an_empty_commit_is_not_landed(self, repo: Path) -> None:
        """Trigger (b) in the shape the repo actually produces.

        The worktree rules mandate an empty claim commit on creation. An empty
        commit has an empty patch-id, so `git cherry` marks it "already
        upstream" against ANY empty commit in base — and empty commits reach
        this base routinely (3 of the last 300, one of them a claim commit).
        The zero-commit test above does not cover this: here `ahead == 1`.
        """
        wt = repo / ".worktrees" / "issue-9999"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "issue-9999", "base")
        _git(wt, "commit", "-q", "--allow-empty", "-m", "chore: claim worktree issue-9999")
        _git(repo, "commit", "-q", "--allow-empty", "-m", "chore(deps): bump npm_and_yarn (#13503)")
        res = run(repo, "--base", "base")
        assert "has landed" not in res.stdout, res.stdout
        assert wt.exists()

    def test_empty_commits_alongside_real_work_do_not_mask_it(self, repo: Path) -> None:
        """A claim commit plus genuine unlanded work must still read as unlanded."""
        wt = repo / ".worktrees" / "issue-8888"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "issue-8888", "base")
        _git(wt, "commit", "-q", "--allow-empty", "-m", "chore: claim worktree issue-8888")
        _commit(wt, "real.txt", "real work\n", "fix(z): genuine work (#9)")
        _git(repo, "commit", "-q", "--allow-empty", "-m", "chore: an empty commit on base")
        res = run(repo, "--base", "base")
        assert "has landed" not in res.stdout, res.stdout
        assert "unlanded commits" in res.stdout

    def test_merge_unique_content_is_never_reported_landed(self, repo: Path) -> None:
        """`git cherry` OMITS merge commits, so merge-only content is unjudgeable.

        A conflict resolution made while updating a branch off base lives only
        in the merge commit. With every non-merge commit landed, the branch
        would otherwise read as fully landed and be marked for deletion while
        carrying work that exists nowhere else. A live branch in this repo
        carries 5 such files today.
        """
        wt = repo / ".worktrees" / "wt-evil"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "wt-evil", "base")
        _commit(wt, "shared.txt", "branch work\n", "fix(a): work (#10)")
        # That commit lands on base as a squash.
        sha = _git(repo, "rev-parse", "wt-evil").stdout.strip()
        _git(repo, "cherry-pick", "--no-commit", sha)
        _git(repo, "commit", "-q", "-m", "fix(a): work (#10) (squashed)")
        # Branch merges base back in, and the merge introduces unique content.
        _git(wt, "merge", "--no-commit", "--no-ff", "base")
        (wt / "merge-only.txt").write_text("resolution work\n", encoding="utf-8")
        _git(wt, "add", "merge-only.txt")
        _git(wt, "commit", "-q", "-m", "merge base into wt-evil")
        res = run(repo, "--base", "base")
        assert "remove it" not in res.stdout, (
            "merge-unique content is invisible to git cherry; a delete "
            f"instruction here destroys it\n{res.stdout}"
        )
        # The safety property above holds for more than one reason, so pin the
        # specific behaviour: the merge must be RECOGNISED as unjudgeable
        # rather than judged on the non-merge commits alone. The pre-fix script
        # reports "unlanded commits" here — safe by luck, not by reasoning.
        assert "cannot be verified" in res.stdout, res.stdout
        assert (wt / "merge-only.txt").exists()

    def test_root_commit_content_is_not_skipped_as_empty(self, repo: Path) -> None:
        """`git diff-tree` prints NOTHING for a parentless commit without --root.

        The empty-commit filter would then treat an unlanded root commit as
        "no evidence" and skip it, leaving `unlanded` at zero while
        `substantive` stays positive from the landed commits — so the branch
        reads as fully landed. Root commits arrive via unrelated-history
        merges (subtree/vendored imports) and shallow-clone boundaries.
        `git cherry` judges them with full-tree semantics, so the two must agree.
        """
        wt = repo / ".worktrees" / "issue-root"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "issue-root", "base")
        _commit(wt, "landed.txt", "landed\n", "fix(a): landed work (#20)")
        sha = _git(wt, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "cherry-pick", "--no-commit", sha)
        _git(repo, "commit", "-q", "-m", "fix(a): landed work (#20) (squashed)")
        # An orphan branch: its first commit has NO parent.
        _git(wt, "checkout", "-q", "--orphan", "vendor")
        _git(wt, "rm", "-q", "-rf", ".")
        (wt / "vendored.py").write_text("VENDORED = 1\n", encoding="utf-8")
        _git(wt, "add", "vendored.py")
        _git(wt, "commit", "-q", "-m", "chore(vendor): import (#21)")
        _git(wt, "checkout", "-q", "issue-root")
        _git(wt, "merge", "-q", "--allow-unrelated-histories", "--no-edit", "vendor")
        res = run(repo, "--base", "base")
        assert "remove it" not in res.stdout, (
            "the vendored root commit is unlanded; deleting this worktree "
            f"destroys it\n{res.stdout}"
        )
        # The safety property above also holds when the merged-PR signal is
        # simply absent, so pin the patch-id verdict itself: the root commit
        # must be SEEN as unlanded. Without --root the pre-fix script reports
        # "looks landed by patch-id" here — safe only because signal 2 was
        # missing, which is not a guarantee.
        assert "unlanded commits" in res.stdout, res.stdout

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
class TestDeletePath:
    """The delete instruction itself — previously unreachable by any test.

    Every other test asserts "remove it" is ABSENT. Without a positive control
    a regression that stopped the script deleting anything would pass the whole
    suite while quietly doing nothing.
    """

    def _landed(self, repo: Path, name: str) -> Path:
        wt = repo / ".worktrees" / name
        _git(repo, "worktree", "add", "-q", str(wt), "-b", name, "base")
        _commit(wt, f"{name}.txt", "work\n", f"fix(x): work in {name} (#30)")
        sha = _git(wt, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "cherry-pick", "--no-commit", sha)
        _git(repo, "commit", "-q", "-m", f"fix(x): work in {name} (#30) (squashed)")
        return wt

    def test_genuinely_landed_worktree_is_marked_for_removal(self, repo: Path) -> None:
        """Positive control: the script must still delete when it should."""
        self._landed(repo, "wt-gone")
        res = run(repo, "--base", "base", merged_pr="4242")
        assert "remove it" in res.stdout, res.stdout
        assert "PR #4242 merged" in res.stdout
        assert res.returncode != 0

    def test_ignored_files_are_named_before_the_instruction(self, repo: Path) -> None:
        """R4c: `git worktree remove` deletes ignored files silently."""
        # .gitignore must exist on base BEFORE the worktree branches from it,
        # or the worktree's checkout lacks it and `.env` reads as untracked —
        # which routes to the dirty-tree branch instead of the ignored one.
        (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
        _git(repo, "add", ".gitignore")
        _git(repo, "commit", "-q", "-m", "chore: ignore .env (#31)")
        wt = self._landed(repo, "wt-secrets")
        (wt / ".env").write_text("TOKEN=xyz\n", encoding="utf-8")
        res = run(repo, "--base", "base", merged_pr="4243")
        assert "IGNORED file" in res.stdout, res.stdout
        assert ".env" in res.stdout

    def test_multi_commit_branch_with_reverted_work_is_not_landed(self, repo: Path) -> None:
        """`git diff-tree` takes at most TWO tree-ishes.

        Passing a whole rev-list made it exit 0 printing nothing for 3+ commits,
        so the content guard was skipped and the branch fell through to landed.
        Every landed fixture in this suite was single-commit, which is exactly
        why that shipped green. 12 of 18 live worktrees are 2+ commits ahead.
        """
        wt = repo / ".worktrees" / "wt-multi"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "wt-multi", "base")
        for n in ("one", "two", "three"):
            _commit(wt, f"{n}.txt", f"{n}\n", f"fix({n}): work (#50)")
        # Base moves first so the picks create NEW commits instead of
        # fast-forwarding (which would leave the branch 0 ahead and never
        # reach the content guard at all).
        _commit(repo, "unrelated2.txt", "y\n", "chore: unrelated (#54)")
        # All three land on base as individual patches...
        for sha in reversed(_git(wt, "rev-list", "base..wt-multi").stdout.split()):
            _git(repo, "cherry-pick", sha)
        # ...then one of them is reverted, so the branch is its only copy.
        _git(repo, "rm", "-q", "two.txt")
        _git(repo, "commit", "-q", "-m", "revert: back out two (#51)")
        res = run(repo, "--base", "base", merged_pr="4250")
        assert "remove it" not in res.stdout, (
            "two.txt was reverted out of base; this worktree is its only copy\n"
            + res.stdout
        )
        assert (wt / "two.txt").exists()

    def test_multi_commit_fully_landed_branch_is_still_removable(self, repo: Path) -> None:
        """Positive control: the multi-commit fix must not just return 'keep' always."""
        wt = repo / ".worktrees" / "wt-multi-ok"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "wt-multi-ok", "base")
        for n in ("p", "q", "r"):
            _commit(wt, f"{n}.txt", f"{n}\n", f"fix({n}): work (#52)")
        # Base moves first, so the picks below create NEW commits rather than
        # fast-forwarding base onto the branch (which would leave it 0 ahead
        # and correctly read as "no commits yet" instead of landed).
        _commit(repo, "unrelated.txt", "x\n", "chore: unrelated (#53)")
        for sha in reversed(_git(wt, "rev-list", "base..wt-multi-ok").stdout.split()):
            _git(repo, "cherry-pick", sha)
        res = run(repo, "--base", "base", merged_pr="4251")
        assert "remove it" in res.stdout, res.stdout

    def test_whitespace_only_fix_is_not_landed_by_patch_id_collision(self, repo: Path) -> None:
        """`git patch-id` STRIPS whitespace, so unrelated whitespace edits collide.

        A dedent that changes behaviour in Python hashes identically to an
        unrelated retab of the same line, and `git cherry` marks it landed
        while the base still holds the bug.
        """
        _commit(repo, "loop.py", "def f(items):\n    acc = 0\n  return acc\n", "chore: seed (#40)")
        wt = repo / ".worktrees" / "wt-ws"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "wt-ws", "base")
        (wt / "loop.py").write_text("def f(items):\n    acc = 0\n    return acc\n", encoding="utf-8")
        _git(wt, "commit", "-q", "-am", "fix(loop): dedent so it returns after the loop (#40)")
        # Base independently retabs the same line — different content, same patch-id.
        (repo / "loop.py").write_text("def f(items):\n    acc = 0\n\treturn acc\n", encoding="utf-8")
        _git(repo, "commit", "-q", "-am", "style: retab (#41)")
        res = run(repo, "--base", "base", merged_pr="4245")
        assert "remove it" not in res.stdout, (
            "base holds a tab, the branch holds 4 spaces — the fix is NOT in base\n"
            + res.stdout
        )

    def test_reverted_work_is_not_still_landed(self, repo: Path) -> None:
        """`git cherry` answers "was it ever applied", not "is it in base now"."""
        wt = self._landed(repo, "wt-reverted")
        _git(repo, "rm", "-q", "wt-reverted.txt")
        _git(repo, "commit", "-q", "-m", "revert: back out #30 (#42)")
        res = run(repo, "--base", "base", merged_pr="4246")
        assert "remove it" not in res.stdout, (
            "the work was reverted out of base; the branch is its only copy\n" + res.stdout
        )
        assert (wt / "wt-reverted.txt").exists()

    def test_locked_worktree_removal_names_the_unlock_step(self, repo: Path) -> None:
        """`git worktree remove` REFUSES on a locked worktree — 15 of 19 are locked.

        Without saying so, the shortest path for the operator is `remove -f -f`,
        which the worktree rules forbid and which destroys ignored files.
        """
        wt = self._landed(repo, "wt-locked")
        _git(repo, "worktree", "lock", str(wt), "--reason", "in use")
        res = run(repo, "--base", "base", merged_pr="4247")
        assert "remove it" in res.stdout, res.stdout
        assert "LOCKED" in res.stdout and "unlock" in res.stdout, res.stdout
        _git(repo, "worktree", "unlock", str(wt))

    def test_tag_shadowing_a_branch_does_not_authorize_deletion(self, repo: Path) -> None:
        """R4b: refs/tags resolves before refs/heads, and the warning is discarded."""
        wt = repo / ".worktrees" / "issue-7"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "issue-7", "base")
        _commit(wt, "landed.txt", "landed\n", "fix(a): landed (#7)")
        sha = _git(wt, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "tag", "issue-7", sha)          # tag shadows the branch name
        _git(repo, "cherry-pick", "--no-commit", sha)
        _git(repo, "commit", "-q", "-m", "fix(a): landed (#7) (squashed)")
        _commit(wt, "unlanded.txt", "NOT landed\n", "fix(b): still open (#7)")
        res = run(repo, "--base", "base", merged_pr="4244")
        assert "remove it" not in res.stdout, (
            "the tag points at the old tip; the BRANCH holds unlanded work\n" + res.stdout
        )
        assert (wt / "unlanded.txt").exists()


@pytest.mark.skipif(not SCRIPT.exists(), reason="verify-done.sh not present")
class TestFailsRatherThanGuesses:
    def test_exit_code_is_nonzero_when_anything_is_unverifiable(self, repo: Path) -> None:
        res = run(repo, "--base", "definitely-not-a-ref")
        assert res.returncode != 0

    def test_clean_repo_with_no_worktrees_passes(self, repo: Path) -> None:
        res = run(repo, "--base", "base")
        assert res.returncode == 0, res.stdout
