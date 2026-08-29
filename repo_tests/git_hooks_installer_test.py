# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Installing a hook from a worktree must survive that worktree's deletion (#14909).

``.git/hooks/pre-push`` was a symlink into ``.worktrees/issue-5142-hooks/``. That
worktree was removed in April; git skips a hook whose target does not resolve,
and it does so silently, so the protected-branch push guard contributed nothing
for months while still looking installed.

#11598 rewrote the installer to copy real files instead of symlinking, and
``tools/git-hooks/install_hooks.sh`` became a shim that delegates to it — but
nothing ever asserted the property, so the only evidence that the class is
closed was that someone had intended to close it. This drives the real
installer, from inside a real linked worktree, then deletes the worktree and
checks the hook still runs.

Asserted on behaviour rather than on the installer's source text: a grep for
``ln -s`` would pass on an installer that had stopped installing anything at
all, which is the same "absent reads as clean" failure the hook itself had.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INSTALLER = _REPO_ROOT / "scripts" / "install-git-hooks.sh"
_TEMPLATES = _REPO_ROOT / "tools" / "git-hooks"
_MANAGED = ("pre-commit", "pre-push")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """#15246: env scrubbed -- an inherited GIT_DIR would point these calls,
    including `worktree add`/`worktree remove`, at the real repository
    instead of the throwaway one under tmp_path.
    """
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=scrubbed_git_env())


def _seed_repo(tmp_path: Path) -> Path:
    """A throwaway repo carrying the real installer and the real templates."""
    repo = tmp_path / "main"
    (repo / "tools" / "git-hooks").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    for name in _MANAGED:
        target = repo / "tools" / "git-hooks" / name
        target.write_bytes((_TEMPLATES / name).read_bytes())
    (repo / "scripts" / "install-git-hooks.sh").write_bytes(_INSTALLER.read_bytes())
    _git(repo.parent, "init", "--quiet", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "--no-verify", "-m", "seed")
    return repo


def _install_from(cwd: Path, repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(cwd / "scripts" / "install-git-hooks.sh")],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@pytest.fixture(name="seeded")
def _seeded(tmp_path: Path) -> Path:
    assert _INSTALLER.is_file(), f"{_INSTALLER} is missing — this guard has no subject"
    for name in _MANAGED:
        assert (_TEMPLATES / name).is_file(), f"template {name} is missing"
    return _seed_repo(tmp_path)


def test_a_hook_installed_from_a_worktree_outlives_that_worktree(seeded: Path, tmp_path: Path) -> None:
    """The exact #14909 sequence: install from a worktree, then delete it."""
    worktree = tmp_path / "linked-wt"
    _git(seeded, "worktree", "add", "--quiet", "-b", "issue-1", str(worktree))

    result = _install_from(worktree, seeded)
    assert result.returncode == 0, result.stdout + result.stderr

    hooks_dir = seeded / ".git" / "hooks"
    for name in _MANAGED:
        installed = hooks_dir / name
        assert installed.exists(), (
            f"{name} was not installed at all — an installer that installs nothing "
            "reads exactly like one that works"
        )
        assert not installed.is_symlink(), (
            f"{name} was installed as a symlink. That is the #11598/#14909 defect: "
            "the link dangles the moment the worktree goes and git skips the hook "
            "without saying anything"
        )
        assert str(worktree) not in installed.read_text(encoding="utf-8"), (
            f"{name}'s installed copy names the worktree it came from, so deleting "
            "that worktree still breaks it"
        )

    _git(seeded, "worktree", "remove", "--force", str(worktree))
    assert not worktree.exists()

    for name in _MANAGED:
        installed = hooks_dir / name
        assert installed.is_file(), f"{name} broke when its source worktree was removed"
        assert os.access(installed, os.X_OK), f"{name} survived but is not executable"
        assert installed.read_bytes() == (_TEMPLATES / name).read_bytes(), (
            f"{name}'s installed copy no longer matches its template"
        )


def test_a_dangling_symlink_left_by_the_old_installer_is_replaced(seeded: Path, tmp_path: Path) -> None:
    """The state the repository was actually found in, repaired by a re-run.

    A developer whose clone still carries the April symlink gets nothing from a
    fix that only handles the fresh-install path.
    """
    hooks_dir = seeded / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    orphan = tmp_path / "deleted-worktree" / "tools" / "git-hooks" / "pre-push"
    (hooks_dir / "pre-push").symlink_to(orphan)
    assert (hooks_dir / "pre-push").is_symlink() and not orphan.exists()

    result = _install_from(seeded, seeded)
    assert result.returncode == 0, result.stdout + result.stderr

    installed = hooks_dir / "pre-push"
    assert not installed.is_symlink(), "the dangling symlink was left in place"
    assert installed.is_file() and os.access(installed, os.X_OK)
    assert installed.read_bytes() == (_TEMPLATES / "pre-push").read_bytes()
