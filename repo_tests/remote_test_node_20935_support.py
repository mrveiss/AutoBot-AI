# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and helpers for the #20935 remote test node suites (``remote_test_node_20935_*_test.py``)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, make_repo

ROOT = repo_root()
TOOL = ROOT / "tools/remote_test_node"
_spec = importlib.util.spec_from_file_location("remote_test_node_run", TOOL / "run.py")
run = importlib.util.module_from_spec(_spec)
sys.modules["remote_test_node_run"] = run
_spec.loader.exec_module(run)
sys.modules.pop("remote_test_node_run", None)  # needed only while the dataclass is built

BASE_ENV = {"AUTOBOT_TEST_NODE_HOST": "h", "AUTOBOT_TEST_NODE_USER": "u"}

FAKE_SSH = """#!/usr/bin/env bash
# Stand-in for ssh: ignores the options and the destination, runs the remote command in $FAKE_HOME.
cd "$FAKE_HOME" || exit 255
args=("$@")
last="${args[${#args[@]}-1]}"
bash -c "$last"
"""


def git_out(cwd: Path, *args: str) -> str:
    return git(cwd, *args).stdout.strip()


def make_node(tmp_path: Path):
    """A fake home with a provisioned mirror and venv, plus a source repo with one commit on main."""
    home, src = tmp_path / "home", tmp_path / "src"
    home.mkdir()
    src.mkdir()
    make_repo(src, default_branch="main")
    (src / "hello.txt").write_text("hi\n", encoding="utf-8")
    git_out(src, "add", "-A")
    git_out(src, "commit", "-q", "-m", "first")
    base = home / "base"
    (base / "venv/bin").mkdir(parents=True)
    (base / "venv/bin/python").symlink_to(sys.executable)
    git_out(home, "init", "-q", "--bare", str(base / "mirror.git"))
    git_out(base, "--git-dir=mirror.git", "remote", "add", "origin", str(src))
    ssh = tmp_path / "fake-ssh"
    ssh.write_text(FAKE_SSH, encoding="utf-8")
    ssh.chmod(0o755)
    env = dict(
        os.environ,
        FAKE_HOME=str(home),
        AUTOBOT_TEST_NODE_HOST="node.invalid",
        AUTOBOT_TEST_NODE_USER="u",
        AUTOBOT_TEST_NODE_BASE="base",
        AUTOBOT_TEST_NODE_SSH_BIN=str(ssh),
        AUTOBOT_TEST_NODE_SLOTS="2",
    )
    return {"home": home, "src": src, "base": base, "env": env, "sha": git_out(src, "rev-parse", "HEAD")}


def run_job(node: dict, *cmd: str, timeout: int = 30) -> subprocess.Popen:
    argv = [sys.executable, str(TOOL / "run.py"), "--sha", node["sha"], "--timeout", str(timeout), "--", *cmd]
    return subprocess.Popen(
        argv, cwd=node["src"], env=node["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )


def leftovers(node: dict) -> list[str]:
    runs = node["base"] / "runs"
    refs = git_out(node["base"], "--git-dir=mirror.git", "for-each-ref", "refs/runs")
    dirs = sorted(os.listdir(runs)) if runs.is_dir() else []
    return dirs + ([refs] if refs else [])


def refs(node: dict) -> set[str]:
    out = git_out(node["base"], "--git-dir=mirror.git", "for-each-ref", "--format=%(refname)", "refs/runs")
    return set(out.split())


def checked_out(node: dict) -> bool:
    runs = node["base"] / "runs"
    return any((runs / name / "tree/hello.txt").is_file() for name in (os.listdir(runs) if runs.is_dir() else []))


def wait_for(pred, secs: float = 20.0) -> bool:
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.2)
    return False
