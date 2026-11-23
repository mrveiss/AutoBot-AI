# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-push interpreter fallback is pinned (#21351), and so are its manual hints (#21346).

``tools/git-hooks/pre-push`` resolves its interpreter preferred-then-floor: one that meets the
``.python-version`` floor AND imports pytest, else any that meets the floor. This drives the REAL
hook through the sandbox ``pre_push_no_open_pr_cap_19397_test`` already builds (its helpers are
imported, not copied), with a ``python3`` stub that is the test's own interpreter minus ``import pytest``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests.pre_push_no_open_pr_cap_19397_test import (
    HOOK_PATH,
    _commit,
    _git,
    _make_sandbox,
    _seed_repo,
)

from autobot_shared.isolated_git import isolated_git_env

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="bash/git not found on this machine -- did not look, not a pass (docs/developer/MEASUREMENT_DISCIPLINE.md)",
)

_REAL_FLOOR = (repo_root() / ".python-version").read_text(encoding="utf-8").strip()
_UNMEETABLE_FLOOR = "99.0"  # no interpreter can meet it
_OVERRIDE = "AUTOBOT_PREPUSH_ALLOW_UNRUNNABLE"
# The one interpreter on the sandbox PATH: the test's own (meets the floor), minus pytest.
_NO_PYTEST_PYTHON = f"""#!/usr/bin/env bash
case "$*" in *"import pytest"*) exit 1;; esac
exec "{sys.executable}" "$@"
"""


def _run_hook(
    tmp_path: Path, *, floor: str = _REAL_FLOOR, selects_tests: bool = False, include_gh: bool = False, **extra_env: str
) -> subprocess.CompletedProcess:
    """Push one new branch through the real hook with a floor-meeting interpreter that lacks pytest."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python3"
    stub.write_text(_NO_PYTEST_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    _make_sandbox(tmp_path, include_gh=include_gh)  # leaves the python3 stub alone: it never overwrites
    (tmp_path / "state").mkdir()
    env = isolated_git_env(
        {
            "PATH": str(bin_dir),
            "HOME": str(tmp_path),
            "PYTHONPATH": str(repo_root()),
            "STATE": str(tmp_path / "state"),
            "OPEN_PR_COUNT": "0",
            "GH_FAIL": "0",
            "AUTOBOT_PREPUSH_FULL": "1",  # the fast gate always needs pytest; this file tests the pytest-stage rules
            **extra_env,
        }
    )
    branch = "interpreter-fallback-test"
    local, _, sha = _seed_repo(tmp_path, env, branch)
    # Untracked on purpose: the pushing repo declares the floor, and a tracked change would be a changed path.
    (local / ".python-version").write_text(f"{floor}\n", encoding="utf-8")
    if selects_tests:
        (local / "sandbox_selected_test.py").write_text("def test_selected():\n    assert True\n", encoding="utf-8")
        _git(local, "add", "sandbox_selected_test.py", env=env)
        sha = _commit(local, env, "second_selection.txt")
    ref = f"refs/heads/{branch}"
    return subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=local,
        input=f"{ref} {sha} {ref} {'0' * 40}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_a_floor_met_interpreter_without_pytest_lets_a_push_that_selects_no_tests_proceed(tmp_path: Path) -> None:
    result = _run_hook(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "BLOCKED" not in result.stderr, result.stderr


def test_no_interpreter_meeting_the_floor_blocks_the_push_naming_the_required_version(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, floor=_UNMEETABLE_FLOOR)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "Push BLOCKED" in result.stderr, result.stderr
    assert f"Python {_UNMEETABLE_FLOOR}+" in result.stderr, result.stderr


def test_selected_tests_with_pytest_not_importable_block_the_push(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, selects_tests=True)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "cannot import pytest" in result.stderr, result.stderr
    assert _OVERRIDE in result.stderr, "the block must name the documented override"


def test_the_unrunnable_override_lets_that_push_proceed_and_says_so(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, selects_tests=True, **{_OVERRIDE: "1"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"allowed by {_OVERRIDE}=1" in result.stderr, result.stderr


@pytest.mark.parametrize("include_gh", [False, True], ids=["gh-not-installed", "no-pr-yet"])
def test_the_manual_validation_hint_prints_the_resolved_interpreter_not_a_variable_name(
    tmp_path: Path, include_gh: bool
) -> None:
    """#21346: both hints name the interpreter the hook resolved (here the sandbox's ``python3``)."""
    result = _run_hook(tmp_path, include_gh=include_gh)

    assert result.returncode == 0, result.stdout + result.stderr
    assert '"python3" scripts/validate_pr_body.py --file <path>' in result.stderr, result.stderr
    assert "PYTEST_PYTHON" not in result.stderr, result.stderr
