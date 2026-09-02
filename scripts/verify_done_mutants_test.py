# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Mutation-directed cases for scripts/verify-done.sh (#13986).

Split from ``verify_done_test.py`` because that file reached the 600-line cap
(``scripts/check_python_file_size.py``), whose rule is to split rather than
grandfather. The two classes here share the harness defined there.

Both cover elements that were mutation-dead: every ``|| return 3`` in
``branch_state`` (a check that cannot run must never become a verdict), and the
two-signal rule (neither patch-id agreement nor a merged PR alone authorizes a
removal).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_done_test import (  # noqa: E402
    CANDIDATE,
    SCRIPT,
    VERDICT,
    _git,
    add_worktree,
    repo,  # noqa: F401  -- fixture, used by name
    run,
)


@pytest.mark.skipif(not SCRIPT.exists(), reason="verify-done.sh not present")
class TestAFailedCheckIsNeverAVerdict:
    """Every ``|| return 3`` in ``branch_state`` reached, one git call at a time.

    The governing property is "a check that cannot run is a FAILURE, never a
    verdict". Nothing exercised it: the suite never made a git call fail, so
    each status check could be deleted with no test noticing (#13986). The shim
    is a real ``git`` for every call but the one named.
    """

    SHIMS = [
        ("tally-diff-tree-fails", "*diff-tree --root -r*", "exit 1"),
        ("cherry-errors-while-printing", "*cherry base*", 'echo \"- HEAD\"; exit 1'),
        ("cherry-succeeds-silently", "*cherry base*", "exit 0"),
        ("merge-rev-list-fails", "*rev-list --merges*", "exit 1"),
        ("touched-rev-list-fails", "* rev-list base..*", "exit 1"),
        ("touched-diff-tree-silently-empty", "*--name-only -z*", "exit 0"),
    ]

    def _landed(self, repo: Path) -> None:
        add_worktree(repo, "wt-shim", [("s.txt", "fix(x): landed work (#22)")])
        sha = _git(repo, "rev-parse", "wt-shim").stdout.strip()
        _git(repo, "cherry-pick", "--no-commit", sha)
        _git(repo, "commit", "-q", "-m", "fix(x): landed work (#22) (squashed)")

    def test_the_control_case_reaches_a_candidate(self, repo: Path) -> None:
        """Without a shim this worktree IS a candidate, so the cases below
        differ by the broken git call and nothing else."""
        self._landed(repo)
        res = run(repo, "--base", "base", merged_pr="4280")
        assert VERDICT["landed"] in res.stdout, res.stdout
        assert CANDIDATE in res.stdout, res.stdout

    @pytest.mark.parametrize(("label", "pattern", "action"), SHIMS, ids=[s[0] for s in SHIMS])
    def test_a_git_call_that_cannot_answer_is_unverifiable(
        self, repo: Path, label: str, pattern: str, action: str
    ) -> None:
        self._landed(repo)
        res = run(repo, "--base", "base", merged_pr="4281", git_shim=(pattern, action))
        assert VERDICT["unverifiable"] in res.stdout, (label, res.stdout)
        assert CANDIDATE not in res.stdout, (label, res.stdout)


@pytest.mark.skipif(not SCRIPT.exists(), reason="verify-done.sh not present")
class TestTwoSignalRule:
    """Neither signal alone authorizes a removal, and the dirty count is real.

    Each case here fails when its element is removed from ``verify-done.sh``;
    the elements were mutation-dead before (#13986).
    """

    def _land(self, repo: Path, name: str, fname: str, subject: str) -> None:
        """Squash-merge ``name``'s single commit into base, as this repo lands work."""
        add_worktree(repo, name, [(fname, subject)])
        sha = _git(repo, "rev-parse", name).stdout.strip()
        _git(repo, "cherry-pick", "--no-commit", sha)
        _git(repo, "commit", "-q", "-m", f"{subject} (squashed)")

    def test_patch_ids_alone_are_not_enough_when_gh_reports_no_merged_pr(self, repo: Path) -> None:
        """The merged-PR half of the two-signal rule, with the signal ANSWERED.

        The stub reports no merged PR, so ``merged PR : none`` — the one value
        the gate must reject. Without the stub this case exits through
        "(not queried)" and proves nothing about the gate.
        """
        self._land(repo, "wt-signal", "s.txt", "fix(x): landed work (#20)")
        res = run(repo, "--base", "base", merged_pr="")
        assert VERDICT["landed"] in res.stdout, res.stdout
        assert "    merged PR     : none" in res.stdout, res.stdout
        assert CANDIDATE not in res.stdout, (
            "patch-id and tree content agree, but no PR merged — one signal is "
            f"never a removal candidate\n{res.stdout}"
        )

    def test_a_path_starting_with_a_colon_is_compared_as_a_literal_path(self, repo: Path) -> None:
        """`git` reads a leading ':' as pathspec magic even after `--`.

        Measured: for a file that HAS changed, `git diff --quiet <base> <branch>
        -- ':loop.py'` exits 0 (the pathspec matched nothing) while
        `:(literal):loop.py` exits 1. So an unquoted colon path turns the
        content check into a silent pass, and the patch-id collision below is
        then the only signal left — which is exactly the one that is wrong.
        """
        (repo / ":loop.py").write_text("def f():\n    acc = 0\n  return acc\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "chore: seed a colon path (#42)")
        wt = repo / ".worktrees" / "wt-colon"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "wt-colon", "base")
        (wt / ":loop.py").write_text("def f():\n    acc = 0\n    return acc\n", encoding="utf-8")
        _git(wt, "commit", "-q", "-am", "fix(loop): dedent the return (#42)")
        # Base independently retabs the same line: different content, same patch-id.
        (repo / ":loop.py").write_text("def f():\n    acc = 0\n\treturn acc\n", encoding="utf-8")
        _git(repo, "commit", "-q", "-am", "style: retab (#43)")
        res = run(repo, "--base", "base", merged_pr="4271")
        assert VERDICT["content moved"] in res.stdout, (
            "base holds a tab and the branch holds 4 spaces, so the content "
            f"check must see the difference on a colon path too\n{res.stdout}"
        )
        assert CANDIDATE not in res.stdout, res.stdout

    def test_uncommitted_work_is_counted_on_a_landed_worktree(self, repo: Path) -> None:
        """The dirty count is reported from the worktree, not assumed zero."""
        self._land(repo, "wt-dirty", "d.txt", "fix(x): landed work (#21)")
        (repo / ".worktrees" / "wt-dirty" / "unsaved.txt").write_text("work\n", encoding="utf-8")
        res = run(repo, "--base", "base", merged_pr="4270")
        assert VERDICT["landed"] in res.stdout, res.stdout
        assert f"{UNCOMMITTED}1" in res.stdout, (
            "an untracked file in the worktree must be counted, not reported as "
            f"0 uncommitted\n{res.stdout}"
        )
        assert CANDIDATE in res.stdout, res.stdout
