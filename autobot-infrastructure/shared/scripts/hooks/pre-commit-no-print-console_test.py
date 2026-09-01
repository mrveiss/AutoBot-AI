# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-print-console (#1082, GH#14151 fail-closed guard).

Issue #14151: see pre-commit-no-direct-redis_test.py's module docstring for
the shared background. This hook's opening banner already references an
unbound color variable under `set -u` (independently closing the
"missing lib/_common.sh" case pre-fix), AND main() calls
`_self_test_strip_significant` before that banner, which already fails
closed if `lib/strip-significant.awk` (a second, sibling dependency) goes
missing — so, like no-direct-redis, only the git-failure path is the
genuine, newly-fixed defect here.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-print-console"

# #14115 AC2: violations the hook finds over every tracked production file.
# Shrink-only -- see TestScanCostAndRepoWideResult for why a silent shrink is
# the bug this pins. Measured, not estimated; the issue's "50" was a staged
# subset, not the tree.
_KNOWN_REPO_VIOLATIONS = 504


def _test_git_env() -> dict[str, str]:
    """#15246: env for every git subprocess this suite spawns.

    Scrubbed rather than os.environ: the pre-push hook runs this suite with
    GIT_DIR pointing at the worktree it is pushing (every checkout here is
    one), and an unscrubbed `git init`/`git add`/`git commit` in a
    fixture then operates on THAT repository instead of tmp_path's. See
    autobot_shared/paths_test.py and #15246 for the reproduced incident.
    """
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=_test_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def test_blocks_print_call(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "bad.py").write_text('print("hi")\n', encoding="utf-8")
    _git(repo, "add", "bad.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode != 0, result.stdout + result.stderr
    assert "print(" in result.stdout


class TestStringStrippingSemantics:
    """#14115: the per-line `awk` strip is what stops a MENTION counting.

    The loop now tests the raw line with bash's own matcher before paying for
    that subprocess. Stripping only ever removes content, so a raw line with no
    candidate cannot produce one once stripped — but nothing covered that
    reasoning, so these pin the two behaviours the shortcut must preserve.
    """

    def test_a_print_inside_a_string_is_not_a_violation(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        (repo / "mention.py").write_text(
            'msg = "call print( ) if you must"\n', encoding="utf-8"
        )
        _git(repo, "add", "mention.py")
        result = subprocess.run(
            ["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env()
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_noqa_comment_suppresses_a_real_call(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        (repo / "noqa.py").write_text('print("allowed")  # noqa\n', encoding="utf-8")
        _git(repo, "add", "noqa.py")
        result = subprocess.run(
            ["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env()
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_real_call_beside_a_string_mention_still_fails(self, tmp_path: Path) -> None:
        """The shortcut must not skip a line that has both."""
        repo = _init_repo(tmp_path)
        (repo / "both.py").write_text(
            'msg = "mentions print( ) here"\nprint("real")\n', encoding="utf-8"
        )
        _git(repo, "add", "both.py")
        result = subprocess.run(
            ["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env()
        )
        assert result.returncode != 0, result.stdout + result.stderr


def test_allows_clean_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "ok.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "ok.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "nothing staged" — reproduced with a genuinely staged violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        (repo / "bad.py").write_text('print("hi")\n', encoding="utf-8")
        _git(repo, "add", "bad.py")
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"


class TestScanCostAndRepoWideResult:
    """#14115 AC1/AC2: the two criteria the optimisation was measured against.

    AC1 asked for a whole-repo scan "in well under a minute" and AC2 for the
    violation set to come back unchanged. Neither is asserted by a crafted
    single-line test, and neither is asserted here by a stopwatch: a wall-clock
    threshold on a shared runner measures contention, not the property, and
    fails the way that teaches people to re-run CI until green (#14157 was
    exactly that defect, in a different suite).

    So the cost claim is pinned structurally instead -- at the thing that made
    it slow -- and the result claim is pinned as a count over the real tree.
    """

    def test_no_subprocess_runs_before_the_raw_line_shortcut(self) -> None:
        """The property that made the scan fast, stated so it cannot regress.

        The old loop paid three subprocesses on EVERY line: an ``awk`` to strip
        strings and two ``grep``s. The fix tests the raw line with bash's own
        matcher first and bails before any of them, so the cost is now per
        *candidate*, not per line -- and candidates are a tiny fraction of a
        repository.

        A command substitution still exists in the loop (``sig=$(...)``) and
        should: stripping is genuinely needed once a line might match. What must
        not come back is a subprocess reached before the shortcut. Asserting
        "no subprocess in the loop" would be wrong and would fail today; the
        real invariant is ordering.
        """
        hook = HOOK_PATH.read_text(encoding="utf-8")
        start = hook.index("_scan_file_for_calls()")
        body = hook[start : hook.index("\n}", start)]

        shortcut = body.index('[[ "$line" =~ $match_regex ]] || continue')
        before = body[:shortcut]

        # `$((` is arithmetic expansion and spawns nothing -- the loop uses it
        # for line_num. Only a real command substitution counts, so the lookahead
        # is load-bearing rather than defensive.
        spawns = re.findall(r"\$\((?!\()|`|\| *(?:grep|awk|sed)\b", before)
        assert not spawns, (
            "a subprocess is spawned before the raw-line shortcut in "
            f"_scan_file_for_calls: {spawns}. That reinstates the per-line cost "
            "#14115 removed -- the hook took minutes over the tree and could not "
            "be used for a whole-repo scan at all."
        )

    @pytest.mark.slow
    def test_the_whole_repo_scan_completes_and_reports_a_known_set(self) -> None:
        """AC2: the repo-wide violation set, pinned.

        The crafted single-line tests prove the semantics on inputs chosen to
        exercise them. They cannot show that the shortcut drops nothing across
        real code, because a dropped detection looks exactly like a file with no
        violations. This runs the hook over every production file in the tree
        and pins the number it finds.

        Shrink-only, in the repo's ratchet idiom: fixing a violation is expected
        and must lower this number in the same commit. A *rise* is a new
        violation; a shrink this constant did not authorise is the optimisation
        silently losing a detection, which is the failure the AC exists to
        catch.
        """
        repo_root = HOOK_PATH.resolve().parents[4]
        tracked = subprocess.run(
            ["git", "ls-files", "*.py", "*.ts", "*.vue"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            env=_test_git_env(),
        ).stdout.split()

        result = subprocess.run(
            ["bash", str(HOOK_PATH), *tracked],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=_test_git_env(),
        )

        found = result.stdout.count("VIOLATION")
        assert found == _KNOWN_REPO_VIOLATIONS, (
            f"whole-repo scan reported {found} violations, expected "
            f"{_KNOWN_REPO_VIOLATIONS}. Higher: new print()/console.* landed. "
            "Lower: either they were fixed -- lower _KNOWN_REPO_VIOLATIONS in "
            "the same commit -- or the scan stopped detecting something, which "
            "is the regression this pins."
        )
