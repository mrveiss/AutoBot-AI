# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Recursive sandbox delete must not take unsaved work with it (#15777).

A dirty-tree guard is a negative assertion, so every refusal test here has a
matching permission test: a guard that refuses everything would pass the first
half and be useless in production.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.sandbox_files import (
    _assert_directory_deletable,
    _enclosing_work_tree,
    _hermetic_git_env,
    _uncommitted_entries,
)


def _init_repo(root: Path) -> None:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    subprocess.run(["git", "init", "-q", str(root)], check=True, env={**env, "PATH": "/usr/bin:/bin"})
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, env={**env, "PATH": "/usr/bin:/bin"})
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True, env={**env, "PATH": "/usr/bin:/bin"})


class TestNonEmptyDirectory:
    @pytest.mark.asyncio
    async def test_non_empty_directory_is_refused_without_recursive(self, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")

        with pytest.raises(HTTPException) as exc:
            await _assert_directory_deletable(tmp_path, "work", recursive=False, force=False)

        assert exc.value.status_code == 409
        assert "1 entries" in exc.value.detail

    @pytest.mark.asyncio
    async def test_empty_directory_still_deletes(self, tmp_path):
        """The pre-existing behaviour for scratch directories is unchanged."""
        await _assert_directory_deletable(tmp_path, "empty", recursive=False, force=False)

    @pytest.mark.asyncio
    async def test_non_empty_directory_passes_with_recursive(self, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")

        await _assert_directory_deletable(tmp_path, "work", recursive=True, force=False)


class TestDirtyWorkTree:
    @pytest.mark.asyncio
    async def test_uncommitted_file_blocks_the_delete(self, tmp_path):
        _init_repo(tmp_path)
        (tmp_path / "unsaved.txt").write_text("hours of work\n", encoding="utf-8")

        with pytest.raises(HTTPException) as exc:
            await _assert_directory_deletable(tmp_path, "repo", recursive=True, force=False)

        assert exc.value.status_code == 409
        assert "uncommitted" in exc.value.detail

    @pytest.mark.asyncio
    async def test_clean_work_tree_is_allowed(self, tmp_path):
        """The other direction: a guard that refuses a clean tree is useless."""
        _init_repo(tmp_path)

        await _assert_directory_deletable(tmp_path, "repo", recursive=True, force=False)

    @pytest.mark.asyncio
    async def test_force_overrides_a_dirty_tree(self, tmp_path):
        _init_repo(tmp_path)
        (tmp_path / "unsaved.txt").write_text("deliberate\n", encoding="utf-8")

        await _assert_directory_deletable(tmp_path, "repo", recursive=True, force=True)

    @pytest.mark.asyncio
    async def test_unverifiable_git_state_fails_closed(self, tmp_path, monkeypatch):
        """git unavailable is 'cannot verify', which must not mean 'go ahead'."""
        _init_repo(tmp_path)

        async def _unanswerable(_work_tree, _target):
            return None

        monkeypatch.setattr("api.sandbox_files._uncommitted_entries", _unanswerable)

        with pytest.raises(HTTPException) as exc:
            await _assert_directory_deletable(tmp_path, "repo", recursive=True, force=False)

        assert exc.value.status_code == 409
        assert "Cannot verify" in exc.value.detail


class TestWorkTreeDiscovery:
    def test_plain_directory_has_no_work_tree(self, tmp_path):
        assert _enclosing_work_tree(tmp_path) is None

    def test_nested_path_resolves_to_the_repo_root(self, tmp_path):
        _init_repo(tmp_path)
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)

        assert _enclosing_work_tree(nested) == tmp_path

    @pytest.mark.asyncio
    async def test_status_lists_untracked_work(self, tmp_path):
        _init_repo(tmp_path)
        (tmp_path / "untracked.txt").write_text("x", encoding="utf-8")

        lines = await _uncommitted_entries(tmp_path, tmp_path)

        assert lines is not None
        assert any(line.startswith("??") for line in lines)


class TestHermeticGitProbe:
    """A probe that inherits GIT_DIR answers about the wrong repository.

    Caught by the pre-push hook, which exports GIT_DIR to everything it runs:
    the clean-tree test saw 9890 uncommitted changes belonging to this repo
    rather than to the temp repo it had just created. In production the same
    inheritance would let the guard permit a delete because an unrelated tree
    happened to be clean.
    """

    def test_inherited_git_vars_are_dropped(self, monkeypatch):
        monkeypatch.setenv("GIT_DIR", "/somewhere/else/.git")
        monkeypatch.setenv("GIT_WORK_TREE", "/somewhere/else")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")

        env = _hermetic_git_env()

        assert not [key for key in env if key.startswith("GIT_") and key != "GIT_OPTIONAL_LOCKS"]
        assert env["LC_ALL"] == "C"
        assert env["PATH"] == "/usr/bin:/bin", "non-git environment must survive"

    @pytest.mark.asyncio
    async def test_status_ignores_an_inherited_git_dir(self, tmp_path, monkeypatch):
        """The regression itself: -C must win over an exported GIT_DIR."""
        _init_repo(tmp_path)
        elsewhere = tmp_path.parent / "elsewhere"
        elsewhere.mkdir()
        _init_repo(elsewhere)
        (elsewhere / "noise.txt").write_text("dirty over there\n", encoding="utf-8")
        monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))

        lines = await _uncommitted_entries(tmp_path, tmp_path)

        assert lines == [], f"probe answered about the wrong repository: {lines}"
