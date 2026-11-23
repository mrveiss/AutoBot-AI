# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared frontend setup action and its two workflow callers (#22114).

``.github/actions/setup-frontend`` is the one home of setup-node on ``.nvmrc``, the npm cache and the dependency install.
ci.yml's ``frontend-tests`` and ``dispatch-preboard-guards.yml``'s ``own-specs`` call it. This file pins the action's
install rules (``npm ci``, the opt-in ``npm install`` fallback, a failed install collected and failing the step after the
loop) and that the two callers pass what each needs. What it does not cover: that the action runs on a runner.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_WORKFLOW = _ROOT / ".github" / "workflows" / "dispatch-preboard-guards.yml"
_SUITE = _ROOT / ".github" / "workflows" / "ci.yml"
_SETUP_ACTION = "./.github/actions/setup-frontend"


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _step(jobs: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in jobs["own-specs"]["steps"] if s.get("name", "").startswith(name))


def _action_step(name: str) -> dict[str, Any]:
    action = yaml.safe_load((_ROOT / ".github/actions/setup-frontend/action.yml").read_text(encoding="utf-8"))
    return next(s for s in action["runs"]["steps"] if s.get("name") == name)


def _ci_setup_inputs() -> dict[str, Any]:
    suite = yaml.safe_load(_SUITE.read_text(encoding="utf-8"))["jobs"]["frontend-tests"]["steps"]
    return next(s for s in suite if s.get("uses") == _SETUP_ACTION)["with"]


def test_node_is_set_up_as_the_frontend_test_job_does_it(jobs) -> None:
    """Both jobs call the ONE setup action (#22114); the action itself holds the setup-node pin, .nvmrc, cache and ``npm ci``."""
    mine = _step(jobs, "Set up the frontend toolchain")["with"]
    theirs = _ci_setup_inputs()
    assert mine["package-dirs"] == "${{ steps.packages.outputs.dirs }}" and mine["allow-install-fallback"] == "true"
    assert "allow-install-fallback" not in theirs, "the test job always installs with npm ci"
    locks = mine["cache-dependency-path"].split()
    assert theirs["cache-dependency-path"] in locks and all((_ROOT / lock).is_file() for lock in locks)
    node = _action_step("Setup Node.js")
    assert node["uses"].startswith("actions/setup-node@") and node["with"]["node-version-file"] == ".nvmrc"
    install = _action_step("Install frontend dependencies")
    assert install["env"]["CYPRESS_INSTALL_BINARY"] == "0" and "npm ci" in install["run"]
    assert "CYPRESS_INSTALL_BINARY" not in jobs["own-specs"]["env"], "the setup action owns it"


def test_the_setup_action_installs_with_npm_ci_where_a_lock_exists_and_npm_install_only_when_allowed() -> None:
    action = yaml.safe_load((_ROOT / ".github/actions/setup-frontend/action.yml").read_text(encoding="utf-8"))
    run = _action_step("Install frontend dependencies")["run"]
    install = (
        'if [ "$ALLOW_FALLBACK" = "true" ] && [ ! -f package-lock.json ]; then npm install || exit 1; '
        "else npm ci || exit 1; fi"
    )
    assert install in run, "inside the subshell that is the left side of `||` errexit is off: each install must exit"
    assert action["inputs"]["allow-install-fallback"]["default"] == "false"


def test_a_failed_install_does_not_stop_the_other_packages_and_fails_the_step_after_the_loop() -> None:
    run = _action_step("Install frontend dependencies")["run"]
    loop_end = run.index("done\n")
    collect = run.index('failed="$failed $dir"')
    assert collect < loop_end, "the failure is collected inside the loop"
    assert "exit 1" not in run[collect:loop_end], "the loop never exits early"
    assert run.index('if [ -n "$failed" ]') > loop_end and run.rstrip().endswith("fi")
