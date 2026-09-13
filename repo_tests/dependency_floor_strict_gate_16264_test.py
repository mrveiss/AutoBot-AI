# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""ci.yml must actually call the --strict floor check, or a new drift lands silently (#16264).

pipeline-scripts/check_dependency_floors.py has carried a ``--strict`` exit
code since #15091, and pipeline-scripts/check_dependency_floors_test.py
already proves that flag turns a planted below-floor pin red
(``TestMainExitCodes.test_strict_run_exits_one_when_below_floor``). What #16264
found missing is a caller: no workflow ever invoked it, so websockets and
langchain-community sat below their declared floors in CI with nothing
reporting it as a failure. This test is the other half of that proof -- that
the workflow itself is wired to the script the unit tests already cover.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_CI = repo_root() / ".github" / "workflows" / "ci.yml"


def _python_shard_steps() -> list[dict]:
    document = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    jobs = document["jobs"]
    assert "python-shard" in jobs, "FIX THE SWEEP: no python-shard job in ci.yml"
    return jobs["python-shard"]["steps"]


def _strict_check_step() -> dict:
    steps = [s for s in _python_shard_steps() if "check_dependency_floors.py" in s.get("run", "")]
    assert len(steps) == 1, f"expected exactly one floor-check step in python-shard, found {len(steps)}"
    return steps[0]


def test_the_strict_flag_is_actually_passed():
    """A call without --strict would run and print, but never fail the job (#16264)."""
    assert "--strict" in _strict_check_step()["run"]


def test_the_check_runs_after_the_ci_environment_is_installed():
    """Must read the CI install, not whatever happened to be on the runner image."""
    steps = _python_shard_steps()
    setup_index = next(i for i, s in enumerate(steps) if s.get("uses", "").endswith("setup-python-suite"))
    check_index = next(i for i, s in enumerate(steps) if "check_dependency_floors.py" in s.get("run", ""))
    assert check_index > setup_index, "the floor check must run after requirements-ci.txt is installed"


def test_the_check_is_not_repeated_on_every_shard():
    """Every shard restores the identical cached venv -- one shard's verdict speaks for all twelve."""
    assert _strict_check_step().get("if") == "matrix.shard == 1"
