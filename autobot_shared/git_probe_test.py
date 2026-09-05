# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The git probe must scrub by construction, not by remembering to (#15783).

The contrast that matters here is not scrubbed-vs-unscrubbed output — it is
that there exists **no** call shape which inherits the ambient environment.
"""

from __future__ import annotations

import subprocess

import pytest

from autobot_shared.git_probe import run_git, start_git
from autobot_shared.paths import AMBIENT_GIT_VARS


def _init_repo(root, monkeypatch=None) -> None:
    from autobot_shared.paths import scrubbed_git_env

    env = {
        **scrubbed_git_env(),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=env)
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True, env=env)


def test_run_git_answers_about_cwd_not_an_inherited_git_dir(tmp_path, monkeypatch):
    """The regression the whole family is made of: -C/cwd must win."""
    _init_repo(tmp_path)
    elsewhere = tmp_path.parent / "elsewhere_run"
    elsewhere.mkdir()
    _init_repo(elsewhere)
    (elsewhere / "dirty.txt").write_text("noise\n", encoding="utf-8")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))

    result = run_git(["status", "--porcelain"], cwd=tmp_path)

    assert result.returncode == 0
    assert result.stdout == "", f"probe answered about the wrong repository: {result.stdout!r}"


def test_argv_excludes_git_itself(tmp_path):
    _init_repo(tmp_path)

    assert run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path).returncode == 0


def test_env_is_refused_rather_than_silently_losing_to_the_scrub():
    """A caller passing env= is making the mistake this module removes."""
    with pytest.raises(TypeError, match="#15783"):
        run_git(["--version"], env={})


@pytest.mark.asyncio
async def test_start_git_refuses_env_too():
    with pytest.raises(TypeError, match="#15783"):
        await start_git("--version", env={})


@pytest.mark.asyncio
async def test_start_git_answers_about_the_repository_it_was_given(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    elsewhere = tmp_path.parent / "elsewhere_async"
    elsewhere.mkdir()
    _init_repo(elsewhere)
    (elsewhere / "dirty.txt").write_text("noise\n", encoding="utf-8")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))

    proc = await start_git("-C", str(tmp_path), "status", "--porcelain")
    stdout, _ = await proc.communicate()

    assert proc.returncode == 0
    assert stdout.decode() == "", "async probe answered about the wrong repository"


def test_every_ambient_variable_is_removed(monkeypatch):
    """Not one of them survives into the child, whatever the caller's shell holds."""
    for name in AMBIENT_GIT_VARS:
        monkeypatch.setenv(name, "/nonexistent/should-not-survive")

    result = run_git(["--version"])

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("git version")
