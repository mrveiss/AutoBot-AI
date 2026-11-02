# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The commit list and the server-side validation of the chosen commit (#20214), against real git."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env
from services.rollback_commits import RollbackRefused, list_candidates, resolve_target

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=scrubbed_git_env({**os.environ, **_GIT_ENV}),
    )
    return out.stdout.strip()


def _commit(repo: Path, name: str, subject: str) -> str:
    (repo / name).write_text(subject, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", subject)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    """main has three commits (origin/main points at the third); a side branch has one more that is not on main."""
    root = tmp_path / "code_source"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    first = _commit(root, "a.txt", "first change")
    second = _commit(root, "b.txt", "second change")
    third = _commit(root, "c.txt", "third change")
    _git(root, "update-ref", "refs/remotes/origin/main", third)
    _git(root, "checkout", "-q", "-b", "side", first)
    side = _commit(root, "d.txt", "never reviewed into main")
    _git(root, "checkout", "-q", "main")
    return {"path": str(root), "first": first, "second": second, "third": third, "side": side, "root": root}


async def test_candidates_are_the_ancestors_of_the_remote_head_with_dates_and_subjects(repo):
    commits = await list_candidates(repo["path"], "origin", "main")
    assert [c.commit for c in commits] == [repo["third"], repo["second"], repo["first"]]
    assert [c.subject for c in commits] == ["third change", "second change", "first change"]
    assert all(c.date.startswith("20") and "T" in c.date for c in commits)
    assert repo["side"] not in [c.commit for c in commits]


async def test_candidate_list_is_capped(repo):
    assert len(await list_candidates(repo["path"], "origin", "main", limit=2)) == 2


async def test_an_ancestor_is_accepted(repo):
    info = await resolve_target(repo["path"], "origin", "main", repo["second"])
    assert (info.commit, info.subject) == (repo["second"], "second change")


async def test_a_commit_that_is_not_an_ancestor_of_the_remote_head_is_refused(repo):
    with pytest.raises(RollbackRefused, match="not part of main"):
        await resolve_target(repo["path"], "origin", "main", repo["side"])


async def test_an_unknown_commit_is_refused(repo):
    with pytest.raises(RollbackRefused, match="not in the code source"):
        await resolve_target(repo["path"], "origin", "main", "0" * 40)


@pytest.mark.parametrize(
    "junk",
    [
        "",
        "main",
        "HEAD",
        "abc123",
        "--output=pwned",
        "-O",
        "--upload-pack=touch pwned",
        "../../etc/passwd",
        "A" * 40,
        "g" * 40,
        ("a" * 40) + "\n",
        "x; touch pwned",
        None,
        12345,
    ],
)
async def test_junk_and_option_like_input_is_refused_before_git_runs(repo, junk):
    with pytest.raises(RollbackRefused, match="Choose a commit from the list"):
        await resolve_target(repo["path"], "origin", "main", junk)
    assert not (repo["root"] / "pwned").exists()
    assert not Path("pwned").exists()


async def test_a_branch_name_that_is_not_a_safe_ref_is_refused(repo):
    with pytest.raises(RollbackRefused):
        await resolve_target(repo["path"], "origin", "--main", repo["second"])
