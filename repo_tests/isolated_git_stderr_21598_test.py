# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failing ``isolated_git.git()`` call names git's own explanation in its message (#21598)."""

import subprocess

import pytest

from autobot_shared.isolated_git import GIT_ERROR_STREAM_LIMIT, GitError, git, make_repo


def test_an_empty_commit_error_carries_gits_stderr(tmp_path):
    repo = make_repo(tmp_path / "scratch")
    git(repo, "commit", "-q", "--allow-empty", "-m", "first")
    with pytest.raises(subprocess.CalledProcessError) as caught:
        git(repo, "commit", "-q", "-m", "second")
    assert "nothing to commit" in str(caught.value)
    assert caught.value.returncode != 0


def test_the_error_message_includes_stderr(tmp_path):
    repo = make_repo(tmp_path / "scratch")
    with pytest.raises(subprocess.CalledProcessError) as caught:
        git(repo, "rev-parse", "--verify", "no-such-ref")
    assert caught.value.stderr.strip()
    assert caught.value.stderr.strip() in str(caught.value)


def test_check_false_returns_the_result_unchanged(tmp_path):
    repo = make_repo(tmp_path / "scratch")
    result = git(repo, "rev-parse", "--verify", "no-such-ref", check=False)
    assert result.returncode != 0


def test_each_stream_in_the_message_is_capped():
    huge = "x" * (GIT_ERROR_STREAM_LIMIT * 3)
    said = str(GitError(1, ["git"], output=huge, stderr=huge)).split(" git said: ", 1)[1]
    assert said.count("x") == 2 * GIT_ERROR_STREAM_LIMIT
    assert said.count("[truncated]") == 2
