# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for autobot_shared.isolated_git (#18940)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from autobot_shared.isolated_git import IDENTITY_EMAIL, git, isolated_git_env, make_repo
from autobot_shared.paths import scrubbed_git_env


@pytest.fixture
def hostile_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A developer machine whose every git config layer fights a fixture."""
    home = tmp_path / "home"
    (home / ".config" / "git").mkdir(parents=True)
    (home / ".config" / "git" / "ignore").write_text("fixture.txt\n", encoding="utf-8")
    hooks = home / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    config = home / ".gitconfig"
    config.write_text(
        f"[init]\n\tdefaultBranch = trunk\n[core]\n\texcludesFile = {home}/ignore\n"
        f"\thooksPath = {hooks}\n[commit]\n\tgpgsign = true\n[user]\n\tname = Dev\n\temail = dev@example.com\n",
        encoding="utf-8",
    )
    (home / "ignore").write_text("fixture.txt\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)
    return home


def test_hostile_global_config_cannot_change_the_built_repo(tmp_path: Path, hostile_home: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / "fixture.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "fixture.txt")
    git(repo, "commit", "-q", "-m", "c")
    assert git(repo, "ls-files").stdout.split() == ["fixture.txt"]
    assert git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert git(repo, "log", "-1", "--format=%ae").stdout.strip() == IDENTITY_EMAIL
    assert "gpgsig" not in git(repo, "cat-file", "-p", "HEAD").stdout


def test_contrast_unisolated_git_is_changed_by_the_same_config(tmp_path: Path, hostile_home: Path) -> None:
    """The fixture is hostile: with only the ambient-variable scrub the same steps differ."""
    repo = tmp_path / "raw"
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", "-C", str(repo), *a], capture_output=True, text=True, env=scrubbed_git_env()
    )
    repo.mkdir()
    assert run("init", "-q").returncode == 0
    # The hostile layers act: the init.defaultBranch layer renames the branch ...
    assert run("symbolic-ref", "--short", "HEAD").stdout.strip() == "trunk"
    (repo / "fixture.txt").write_text("x\n", encoding="utf-8")
    # ... and the global excludesFile makes `git add` refuse the fixture, so nothing is tracked.
    added = run("add", "fixture.txt")
    assert added.returncode != 0 and "ignored" in added.stderr
    assert run("ls-files").stdout.split() == []


def test_env_drops_ambient_and_inherited_names() -> None:
    base = {
        "GIT_DIR": "/x",
        "GIT_WORK_TREE": "/y",
        "GIT_INDEX_FILE": "/z",
        "GIT_AUTHOR_NAME": "a",
        "GIT_CONFIG_COUNT": "9",
        "PATH": "/bin",
    }
    env = isolated_git_env(base)
    assert not {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} & env.keys()
    assert env["PATH"] == "/bin"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull and env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_AUTHOR_NAME"] != "a" and env["GIT_CONFIG_COUNT"] != "9"


def test_identity_false_leaves_author_to_repo_config() -> None:
    assert not [k for k in isolated_git_env({}, identity=False) if k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))]
