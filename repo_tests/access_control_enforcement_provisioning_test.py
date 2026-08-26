# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The provisioning role actually runs the enforcement-mode seeder (#14866).

A writer nothing invokes is the defect this issue is about, one layer up: the
only automated writer of ``feature_flag:access_control:enforcement_mode`` was a
deployment script importing a package that does not exist, executed with its
output discarded. So the seeder existing is not the deliverable -- the
provisioning path reaching it is.

These checks are structural on purpose. They run in CI, where no host, no Redis
and no Ansible are available, and they assert the three things that can silently
drift: the role includes the task, the task names a script that exists, and the
two independent statements of the posture default (Ansible's and Python's) still
agree.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from services.feature_flags import PROVISIONED_ENFORCEMENT_MODE_DEFAULT, EnforcementMode

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROLE = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "access_control"
_SEEDER = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "security" / "seed_enforcement_mode.py"
_SEEDER_REPO_PATH = "autobot-infrastructure/shared/scripts/security/seed_enforcement_mode.py"


def _load_yaml(path: Path):
    assert path.exists(), f"{path.relative_to(_REPO_ROOT)} is missing"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def role_defaults() -> dict:
    return _load_yaml(_ROLE / "defaults" / "main.yml")


@pytest.fixture(scope="module")
def enforcement_tasks() -> list:
    tasks = _load_yaml(_ROLE / "tasks" / "enforcement_mode.yml")
    assert tasks, "the enforcement-mode task file must not be empty"
    return tasks


@pytest.fixture(scope="module")
def seeder_module():
    spec = importlib.util.spec_from_file_location("seed_enforcement_mode", _SEEDER)
    assert spec and spec.loader, f"{_SEEDER_REPO_PATH} is not importable"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheRoleReachesTheSeeder:
    """An install-time writer is only a writer if provisioning calls it."""

    def test_the_role_includes_the_enforcement_mode_tasks(self):
        main_tasks = _load_yaml(_ROLE / "tasks" / "main.yml")
        assert main_tasks, "the role's task list must not be empty"

        included = [task.get("include_tasks") for task in main_tasks if task.get("include_tasks")]
        assert included, "no task file is included at all -- this check would pass vacuously"
        assert "enforcement_mode.yml" in included

    def test_the_task_runs_the_seeder_that_exists(self, enforcement_tasks, role_defaults):
        commands = [task["ansible.builtin.command"] for task in enforcement_tasks if "ansible.builtin.command" in task]
        assert commands, "the enforcement-mode task file runs no command at all"

        argv = [str(item) for command in commands for item in command.get("argv", [])]
        assert argv, "the command task passes no argv"
        assert any("access_control_enforcement_seeder" in item for item in argv)

        seeder_var = role_defaults["access_control_enforcement_seeder"]
        assert _SEEDER_REPO_PATH in seeder_var, "the role points at a path this repository does not carry"
        assert _SEEDER.exists()

    def test_the_task_passes_the_configured_posture(self, enforcement_tasks):
        commands = [task["ansible.builtin.command"] for task in enforcement_tasks if "ansible.builtin.command" in task]
        argv = [str(item) for command in commands for item in command.get("argv", [])]

        assert "--mode" in argv, "the role must state the posture rather than rely on the seeder's own default"
        assert any("access_control_enforcement_mode" in item for item in argv)

    def test_a_missing_seeder_stops_the_run(self, enforcement_tasks):
        """Silently continuing without a posture is the defect itself."""
        failures = [task for task in enforcement_tasks if "ansible.builtin.fail" in task]
        assert failures, "nothing fails the run when the provisioner is absent"


class TestTheTwoStatementsOfTheDefaultAgree:
    """The same drift #13335 found in the service-auth block: an Ansible role and
    a Pydantic/module default stating the same thing differently, so an install
    provisioned by one route ends up in a different posture than the other."""

    def test_the_role_default_matches_the_python_default(self, role_defaults):
        assert role_defaults["access_control_enforcement_mode"] == PROVISIONED_ENFORCEMENT_MODE_DEFAULT.value

    def test_the_role_default_is_a_mode_the_platform_recognises(self, role_defaults):
        valid = {mode.value for mode in EnforcementMode}
        assert valid, "an empty mode enumeration would make this assertion meaningless"
        assert role_defaults["access_control_enforcement_mode"] in valid


class TestTheExitCodeContractIsSharedNotRestated:
    """The role decides ``changed`` from the seeder's exit code. If either side
    renumbers, a seeding run reports 'ok' and nobody notices the flag moved."""

    def test_the_seeder_publishes_distinct_outcomes(self, seeder_module):
        codes = {
            seeder_module.EXIT_UNCHANGED,
            seeder_module.EXIT_FAILED,
            seeder_module.EXIT_SEEDED,
        }
        assert len(codes) == 3, "the three provisioning outcomes must be distinguishable"

    def test_the_role_reports_changed_on_the_seeded_code(self, enforcement_tasks, seeder_module):
        changed_when = [task["changed_when"] for task in enforcement_tasks if "changed_when" in task]
        assert changed_when, "no task states when provisioning counts as a change"
        assert any(f"== {seeder_module.EXIT_SEEDED}" in str(expr) for expr in changed_when)

    def test_the_role_treats_only_the_two_success_codes_as_success(self, enforcement_tasks, seeder_module):
        failed_when = [task["failed_when"] for task in enforcement_tasks if "failed_when" in task]
        assert failed_when, "no task states when provisioning has failed"

        expression = " ".join(str(expr) for expr in failed_when)
        assert f"[{seeder_module.EXIT_UNCHANGED}, {seeder_module.EXIT_SEEDED}]" in expression
        assert str(seeder_module.EXIT_FAILED) not in expression.split("[", 1)[1]
