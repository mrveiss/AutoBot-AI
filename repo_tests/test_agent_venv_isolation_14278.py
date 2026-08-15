# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every component installs into the interpreter its unit runs (#14278).

The agent installed into system Python with `--break-system-packages`, so a
transitive dependency the distro owns could not be replaced:

    ERROR: Cannot uninstall typing_extensions 4.10.0, RECORD file not found.
           Hint: The package was installed by debian.

Provisioning an external node stopped there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROLES = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles"


def _pip_tasks() -> list[tuple[str, dict]]:
    """(role file, pip task args) for every ansible pip task in the roles tree."""
    found = []
    for path in sorted(_ROLES.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover
            continue

        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                pip = node.get("ansible.builtin.pip") or node.get("pip")
                if isinstance(pip, dict):
                    found.append((str(path.relative_to(_ROLES)), pip))
                for value in node.values():
                    walk(value)

        walk(document)
    return found


def test_the_scan_found_pip_tasks():
    """An empty scan makes every rule below vacuous."""
    assert len(_pip_tasks()) >= 4


def test_no_role_installs_into_system_python_with_break_system_packages():
    """`--break-system-packages` lets pip WRITE to the system environment. It does
    not let pip remove what dpkg owns, so any distro-managed transitive
    dependency aborts the install."""
    offenders = [
        f"{role_file}: {pip.get('name')}"
        for role_file, pip in _pip_tasks()
        if "break-system-packages" in str(pip.get("extra_args") or "")
    ]

    assert offenders == [], "\n".join(offenders)


def test_the_agent_installs_into_a_virtualenv():
    tasks = [pip for role_file, pip in _pip_tasks() if role_file.startswith("slm_agent/")]

    assert tasks, "no pip task found in the slm_agent role"
    assert all(task.get("virtualenv") for task in tasks), "the agent still installs outside a venv"


def test_the_agent_unit_runs_the_venv_interpreter():
    """The install target and the running interpreter must be the same one.

    A venv that the unit does not use is worse than no venv: the dependencies are
    installed somewhere nothing imports from, and the failure appears at runtime
    rather than at install time.
    """
    unit = (_ROLES / "slm_agent" / "templates" / "slm-agent.service.j2").read_text(encoding="utf-8")
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))

    defaults = yaml.safe_load(
        (_ROLES / "slm_agent" / "defaults" / "main.yml").read_text(encoding="utf-8")
    )
    venv_var = "slm_agent_venv"

    assert "/usr/bin/python3" not in exec_start
    # The unit references the venv by VARIABLE, so assert on that rather than on
    # a literal path — the template never contains the resolved directory.
    assert venv_var in exec_start, f"ExecStart does not use {{{{ {venv_var} }}}}: {exec_start}"
    assert defaults[venv_var].endswith("/venv")


def test_the_unit_still_sets_pythonpath_for_autobot_shared():
    """#11508: the agent imports autobot_shared from the install base rather than
    borrowing another component's venv. Moving to its own venv must not lose
    that — PYTHONPATH is honoured by any interpreter, so it should be untouched.
    """
    unit = (_ROLES / "slm_agent" / "templates" / "slm-agent.service.j2").read_text(encoding="utf-8")

    assert re.search(r"^Environment=PYTHONPATH=.*slm_agent_dir", unit, re.MULTILINE)


def test_the_venv_path_is_derived_from_the_install_dir():
    """A hardcoded second path would drift from slm_agent_dir."""
    defaults = yaml.safe_load(
        (_ROLES / "slm_agent" / "defaults" / "main.yml").read_text(encoding="utf-8")
    )

    assert "slm_agent_dir" in str(defaults.get("slm_agent_venv", ""))
