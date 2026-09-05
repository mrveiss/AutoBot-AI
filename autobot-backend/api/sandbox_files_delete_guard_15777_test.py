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

import asyncio
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import sandbox_files
from api.sandbox_files import (
    _assert_directory_deletable,
    _enclosing_work_tree,
    _hermetic_git_env,
    _uncommitted_entries,
)
from autobot_shared.paths import scrubbed_git_env


def _fixture_git_env() -> dict[str, str]:
    """The canonical scrub, plus the identity a throwaway repo needs to commit.

    Wrapping rather than inlining ``{**scrubbed_git_env(), ...}`` at three call
    sites is the pattern ``check_git_write_env_scrubbed`` expects: without the
    scrub, an ambient ``GIT_DIR`` -- which the pre-push hook exports -- makes
    these writes land in the pushing worktree's real index rather than in
    ``tmp_path`` (#15246).
    """
    return {
        **scrubbed_git_env(),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=_fixture_git_env())
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, env=_fixture_git_env())
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True, env=_fixture_git_env())


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
        # Both repositories live inside this test's own tmp_path: writing the
        # second into tmp_path.parent leaves an artefact in the shared session
        # base and makes a rerun in the same session fail on mkdir.
        target = tmp_path / "target"
        elsewhere = tmp_path / "elsewhere"
        for repo in (target, elsewhere):
            repo.mkdir()
            _init_repo(repo)
        (elsewhere / "noise.txt").write_text("dirty over there\n", encoding="utf-8")
        monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))

        lines = await _uncommitted_entries(target, target)

        assert lines == [], f"probe answered about the wrong repository: {lines}"


class TestTheTimeoutKillsWhatItBounds:
    """`asyncio.wait_for` abandons the await, not the child (#15777 review).

    Without an explicit kill, the timeout that exists to bound a hung
    `git status` leaks one orphan per timeout -- on exactly the lock-contended
    or network-mounted work tree that makes timeouts happen at all.
    """

    @pytest.mark.asyncio
    async def test_a_hung_probe_is_killed_and_reaped(self, tmp_path, monkeypatch):
        killed = {"kill": 0, "wait": 0}

        class _HungProcess:
            returncode = None

            async def communicate(self):
                await asyncio.sleep(3600)

            def kill(self):
                killed["kill"] += 1

            async def wait(self):
                killed["wait"] += 1

        async def _spawn(*_args, **_kwargs):
            return _HungProcess()

        monkeypatch.setattr(sandbox_files.asyncio, "create_subprocess_exec", _spawn)
        monkeypatch.setattr(sandbox_files, "_GIT_STATUS_TIMEOUT_SECONDS", 0.01)

        result = await sandbox_files._uncommitted_entries(tmp_path, tmp_path)

        assert result is None, "an unanswerable probe still reports 'cannot verify'"
        assert killed["kill"] == 1, "the child was abandoned, not killed"
        assert killed["wait"] == 1, "the killed child was never reaped"

    @pytest.mark.asyncio
    async def test_a_spawn_failure_is_cannot_verify_not_a_crash(self, tmp_path, monkeypatch):
        """The other half of the branch that produces None (#15777 review minor)."""

        async def _no_git(*_args, **_kwargs):
            raise FileNotFoundError("git")

        monkeypatch.setattr(sandbox_files.asyncio, "create_subprocess_exec", _no_git)

        assert await sandbox_files._uncommitted_entries(tmp_path, tmp_path) is None

    @pytest.mark.asyncio
    async def test_an_already_exited_process_is_not_killed_again(self, tmp_path):
        class _Exited:
            returncode = 0

            def kill(self):  # pragma: no cover - must not be reached
                raise AssertionError("a process that already exited must not be killed")

        await sandbox_files._terminate(_Exited())


class TestTheAuditLineSurvivesTheFloodGuard:
    @pytest.mark.asyncio
    async def test_the_audit_call_is_flood_exempt(self, tmp_path, monkeypatch):
        """The interaction the review found, pinned where it was introduced.

        Without ``flood_exempt`` this call site collapses to one suppression key
        for every delete, so a burst loses its audit trail from the sixth on.
        """
        recorded = {}

        def _warning(*args, **kwargs):
            recorded["extra"] = kwargs.get("extra")

        monkeypatch.setattr(sandbox_files.logger, "warning", _warning)
        monkeypatch.setattr(sandbox_files, "_validate_path", lambda path: tmp_path)
        monkeypatch.setattr(sandbox_files, "_check_permission", lambda request, permission: {"username": "agent"})
        monkeypatch.setattr(sandbox_files.shutil, "rmtree", lambda target: None)
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")

        await sandbox_files.delete_file.__wrapped__(request=None, path="work", recursive=True, force=True)

        assert recorded["extra"] == {"flood_exempt": True}


class TestTheSandboxRootBound:
    def test_discovery_stops_at_the_sandbox_root(self, tmp_path, monkeypatch):
        """A checkout *above* the sandbox root must not capture every delete.

        On a developer machine the sandbox often sits inside a clone, so without
        this bound `_enclosing_work_tree` walks up into it and the dirty-tree
        guard refuses deletes over unrelated uncommitted work. Both other
        discovery tests run outside `SANDBOX_FILES_ROOT`, so the break was never
        taken.
        """
        checkout = tmp_path / "checkout"
        (checkout / ".git").mkdir(parents=True)
        sandbox_root = checkout / "sandbox"
        target = sandbox_root / "scratch"
        target.mkdir(parents=True)
        monkeypatch.setattr(sandbox_files, "SANDBOX_FILES_ROOT", sandbox_root)

        assert sandbox_files._enclosing_work_tree(target) is None

    def test_a_repository_inside_the_sandbox_is_still_found(self, tmp_path, monkeypatch):
        """The contrast: the bound stops the walk, it does not disable it."""
        sandbox_root = tmp_path / "sandbox"
        repo = sandbox_root / "work"
        (repo / ".git").mkdir(parents=True)
        monkeypatch.setattr(sandbox_files, "SANDBOX_FILES_ROOT", sandbox_root)

        assert sandbox_files._enclosing_work_tree(repo) == repo
