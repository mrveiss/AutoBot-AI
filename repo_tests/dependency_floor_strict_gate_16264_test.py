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

#16394: python-shard now calls the checker TWICE -- once for the backend venv,
once for the SLM venv it built itself -- each scoped with --roots to what that
venv actually installs (see ci.yml's own comments on those two steps for why).
Both must carry --strict and both must stay gated to shard 1 only, so this file
covers each named step rather than assuming exactly one.
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


def _strict_check_steps() -> list[dict]:
    steps = [s for s in _python_shard_steps() if "check_dependency_floors.py" in s.get("run", "")]
    assert (
        len(steps) == 2
    ), f"expected exactly two floor-check steps in python-shard (backend + SLM, #16394), found {len(steps)}"
    return steps


def test_the_strict_flag_is_actually_passed_by_both_checks():
    """A call without --strict would run and print, but never fail the job (#16264)."""
    for step in _strict_check_steps():
        assert "--strict" in step["run"], step["name"]


def test_each_check_is_scoped_to_the_venv_it_runs_under():
    """#16394: each check reads --roots the OTHER venv's requirements file is absent from.

    Otherwise the backend check would judge SLM's declared websockets floor
    against the backend venv's capped install (or vice versa), reintroducing
    the exact cross-venv shortfall KNOWN_CROSS_VENV_EXEMPTIONS used to paper
    over -- scoping is what makes that exemption unnecessary rather than just
    quieter.
    """
    backend_step, slm_step = _strict_check_steps()
    assert "autobot-slm-backend/requirements.txt" not in backend_step["run"]
    assert "--roots" in backend_step["run"]
    assert "autobot-backend/requirements.txt" not in slm_step["run"]
    assert "autobot-slm-backend/requirements.txt" in slm_step["run"]


def test_the_slm_check_runs_under_the_slm_venvs_own_interpreter():
    """Otherwise it would just re-check the backend venv a second time for nothing."""
    _, slm_step = _strict_check_steps()
    assert "outputs.slm-venv" in slm_step["run"]


def test_the_checks_run_after_the_ci_environment_is_installed():
    """Must read the CI install, not whatever happened to be on the runner image."""
    steps = _python_shard_steps()
    setup_index = next(i for i, s in enumerate(steps) if s.get("uses", "").endswith("setup-python-suite"))
    for step in _strict_check_steps():
        check_index = steps.index(step)
        assert check_index > setup_index, "the floor check must run after requirements-ci.txt is installed"


def test_neither_check_is_repeated_on_every_shard():
    """Every shard restores the identical cached venv(s) -- one shard's verdict speaks for all twelve."""
    for step in _strict_check_steps():
        assert step.get("if") == "matrix.shard == 1", step["name"]
