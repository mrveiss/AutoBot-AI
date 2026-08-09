#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the Ansible repo-path reference guard (#13744).

The bug this guards against — a play installing from
``/opt/autobot/src/docker/npu-worker/requirements.txt``, which never existed —
survived because a wrong path in a play only fails on a host. A guard for it is
worth nothing unless it can actually fail, so these tests assert both directions
and the discovery step, which is where the first draft silently checked nothing.
"""

import pathlib
import subprocess
import sys

import pytest

_SCRIPT = pathlib.Path(__file__).parent / "check_ansible_file_references.py"
sys.path.insert(0, str(_SCRIPT.parent))

import check_ansible_file_references as guard  # noqa: E402


def _play(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    """Write a play at a realistic ansible/ location under *tmp_path*."""
    play_dir = tmp_path / "component" / "ansible" / "playbooks"
    play_dir.mkdir(parents=True)
    path = play_dir / "deploy.yml"
    path.write_text(body, encoding="utf-8")
    return path


# ----------------------------------------------------------------- discovery


def test_a_checkout_inside_an_excluded_directory_is_still_scanned(tmp_path):
    """The repo may live at .worktrees/<branch>/ — exclusions are relative.

    Matching ``_EXCLUDE_DIRS`` against the absolute path excluded the whole
    repository and made the guard report "0 references" while passing.
    """
    root = tmp_path / ".worktrees" / "issue-1"
    _play(root, "- hosts: all\n")

    assert guard._ansible_files(root), "the guard scanned nothing from inside a worktree"


def test_vendored_trees_are_still_skipped(tmp_path):
    _play(tmp_path / "node_modules" / "pkg", "- hosts: all\n")

    assert guard._ansible_files(tmp_path) == []


def test_only_ansible_paths_are_scanned(tmp_path):
    other = tmp_path / "compose"
    other.mkdir()
    (other / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    assert guard._ansible_files(tmp_path) == []


# ---------------------------------------------------------------- extraction


def test_a_deployed_src_reference_is_extracted():
    text = "    - pip:\n        requirements: /opt/autobot/src/autobot-npu-worker/requirements.txt\n"

    assert guard._referenced_repo_paths(text) == [(2, "requirements", "autobot-npu-worker/requirements.txt")]


@pytest.mark.parametrize(
    "line",
    [
        "        requirements: /etc/somewhere/else/requirements.txt",
        "        src: {{ project_root }}/requirements.txt",
        "        src: ${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/",
    ],
)
def test_paths_that_cannot_be_resolved_statically_are_skipped(line):
    """A guard that reports false positives gets switched off."""
    assert guard._referenced_repo_paths(line + "\n") == []


# ------------------------------------------------------------- end-to-end


def _run(cwd: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_missing_referenced_file_fails(tmp_path):
    _play(
        tmp_path,
        "- hosts: all\n  tasks:\n    - pip:\n        requirements: /opt/autobot/src/docker/npu-worker/requirements.txt\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "docker/npu-worker/requirements.txt" in result.stdout


def test_a_present_referenced_file_passes(tmp_path):
    (tmp_path / "autobot-npu-worker").mkdir()
    (tmp_path / "autobot-npu-worker" / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    _play(
        tmp_path,
        "- hosts: all\n  tasks:\n    - pip:\n        requirements: /opt/autobot/src/autobot-npu-worker/requirements.txt\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "1 deployed-src reference(s) resolve" in result.stdout


def test_the_real_repository_passes():
    """The guard must be green on the tree it ships with."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    result = _run(repo_root)

    assert result.returncode == 0, result.stdout
    # And it must be checking something — "0 references" would be a guard that cannot fail.
    assert "0 deployed-src reference(s)" not in result.stdout
