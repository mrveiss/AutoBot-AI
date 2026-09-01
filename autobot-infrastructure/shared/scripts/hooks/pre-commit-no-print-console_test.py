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

import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-print-console"


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
