# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""branch-cleanup must keep closed-issue branches with unlanded changes (#21798).

A merged PR closing the issue does not prove the branch's own commits reached
main. ``branch_has_no_unlanded_changes`` requires the merge of the branch into
base to equal base's tree before the cleanup step may delete it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import isolated_git_env
from tools.lint._comment_syntax import code_text

_ROOT = repo_root()
_GUARD_LIB = _ROOT / "scripts/lib/branch-guards.sh"
_WORKFLOW = _ROOT / ".github/workflows/branch-cleanup.yml"


def _git_version() -> tuple[int, int]:
    out = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


_NO_MERGE_TREE = _git_version() < (2, 38)
_IN_CI = os.environ.get("CI", "").strip().lower() not in ("", "0", "false", "no")
_MERGE_TREE_REASON = "git merge-tree --write-tree needs git >= 2.38 (the runner has it)"


def _require_merge_tree() -> None:
    """Skip locally on old git; under CI a skip would hide a broken guard, so fail."""
    if _NO_MERGE_TREE:
        if _IN_CI:
            pytest.fail(f"CI must not skip the merge-tree guard tests: {_MERGE_TREE_REASON}")
        pytest.skip(_MERGE_TREE_REASON)


@pytest.fixture
def needs_merge_tree() -> None:
    _require_merge_tree()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, env=isolated_git_env())


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _commit_on(repo: Path, branch: str, name: str, text: str) -> None:
    _git(repo, "checkout", "-qb", branch)
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"work {branch}")
    _git(repo, "checkout", "-q", "main")


def _guard(repo: Path, ref: str) -> subprocess.CompletedProcess[str]:
    script = f'source "{_GUARD_LIB}"\nbranch_has_no_unlanded_changes main "{ref}"\n'
    return subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True, env=isolated_git_env())


@pytest.mark.usefixtures("needs_merge_tree")
def test_branch_with_unlanded_changes_is_kept(tmp_path) -> None:
    repo = _repo(tmp_path)
    _commit_on(repo, "issue-1", "new.txt", "never landed\n")
    res = _guard(repo, "issue-1")
    assert res.returncode == 1
    assert "SKIP" in res.stdout


@pytest.mark.usefixtures("needs_merge_tree")
def test_conflicting_branch_is_kept(tmp_path) -> None:
    repo = _repo(tmp_path)
    _commit_on(repo, "issue-2", "a.txt", "branch\n")
    (repo / "a.txt").write_text("main\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "main moves")
    assert _guard(repo, "issue-2").returncode == 1


@pytest.mark.usefixtures("needs_merge_tree")
def test_branch_whose_merge_equals_main_is_deletable(tmp_path) -> None:
    repo = _repo(tmp_path)
    _commit_on(repo, "issue-3", "new.txt", "landed\n")
    # Squash-land the same content on main: not an ancestor, same tree.
    (repo / "new.txt").write_text("landed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "squash (#3)")
    res = _guard(repo, "issue-3")
    assert res.returncode == 0, res.stdout
    assert "SKIP" not in res.stdout


def test_unresolvable_ref_is_kept(tmp_path) -> None:
    assert _guard(_repo(tmp_path), "no-such-branch").returncode == 1


def test_workflow_gates_deletion_on_the_guard() -> None:
    text = _WORKFLOW.read_text(encoding="utf-8")
    step = text.split("Delete branches for closed issues", 1)[1].split("Run cleanup script", 1)[0]
    code = code_text(step, name="step.sh")
    assert code.index("branch_has_no_unlanded_changes") < code.index("git push origin --delete")
