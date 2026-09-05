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

from autobot_shared import git_probe
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


def test_the_child_environment_is_asserted_directly(monkeypatch):
    """Inspect the env actually handed to the child, not a proxy for it.

    `git --version` reads no repository state, so it succeeds whether or not
    the scrub happened -- a regression that forwarded the whole environment
    would pass a test that only checked the exit code. Capturing the `env=`
    argument is the property the guard actually promises (#15783 review).
    """
    for name in (*AMBIENT_GIT_VARS, "GIT_SSH_COMMAND", "GIT_CONFIG_COUNT", "GIT_NAMESPACE"):
        monkeypatch.setenv(name, "should-not-survive")
    captured = {}

    def _capture(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(git_probe.subprocess, "run", _capture)
    run_git(["status"])

    leaked = [name for name in captured["env"] if name.startswith("GIT_")]
    assert leaked == [], f"these reached the child: {leaked}"
    assert captured["argv"][0] == "git"
    assert "PATH" in captured["env"], "the non-git environment must survive"


def test_the_ambient_scrub_is_still_reachable_and_narrower(monkeypatch):
    """The contrast: strict=False keeps GIT_ names that are not ambient.

    Without this the strict default could be a no-op difference and the test
    above would still pass.
    """
    monkeypatch.setenv("GIT_DIR", "/should-not-survive")
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -o Foo=bar")
    captured = {}

    def _capture(argv, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(git_probe.subprocess, "run", _capture)
    run_git(["status"], strict=False)

    assert "GIT_DIR" not in captured["env"], "the ambient scrub still applies"
    assert captured["env"].get("GIT_SSH_COMMAND") == "ssh -o Foo=bar"


def test_git_still_runs_under_the_strict_environment():
    """The behavioural half: stripping every GIT_ name does not break git."""
    result = run_git(["--version"])

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("git version")
