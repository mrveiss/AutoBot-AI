# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No site that installs OpenVINO may contradict the SSOT (#14447, #14452, #14453).

Three sites install `openvino` independently of `autobot-npu-worker/requirements.txt`
(the SSOT): the `npu-worker` ansible role's inline package list, the
`deploy-native-services.yml` playbook's inline package list, and the standalone
`requirements-npu.txt` consumed by dependabot. All three drifted the same way: a
floor below the SSOT's, plus `openvino-dev` -- a deprecated meta-package frozen at
2024.6.0 with no release compatible with openvino 2026.x.

pip therefore backtracked through every openvino-dev version down to 2022.3.2, each
pinning numpy lower, until it reached numpy==1.25.2, which has no cp314 wheel. The
sdist build failed with `Cannot import 'setuptools.build_meta'` -- an error that
names the build backend and nothing else. Provisioning was dead with no indication
of which requirement caused it.

The floor is read out of the SSOT rather than repeated here. A test that hardcoded
`2026.3.0` would go stale in exactly the way each site did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ROLE_TASKS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "npu-worker" / "tasks" / "main.yml"
_PLAYBOOK = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "deploy-native-services.yml"
_DOCKER_REQUIREMENTS = _REPO_ROOT / "autobot-infrastructure" / "autobot-npu-worker" / "docker" / "requirements-npu.txt"
_SSOT_REQUIREMENTS = _REPO_ROOT / "autobot-npu-worker" / "requirements.txt"

_ROLE_TASK_NAME = "Install OpenVINO and dependencies"
_PLAYBOOK_TASK_NAME = "Install OpenVINO runtime for NPU Worker"


@dataclass(frozen=True)
class _Site:
    """One place in the repo that installs OpenVINO independently of the SSOT."""

    label: str
    packages: list
    extra_args: str


def _bare_name(spec: str) -> str:
    """Strip extras/markers/version specifiers, leaving the distribution name."""
    return re.split(r"[<>=\[]", spec)[0].strip()


def _version_tuple(spec: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", spec)[:3])


def _pip_task_from_task_list(tasks: list, task_name: str, module_key: str) -> dict:
    for task in tasks or []:
        if isinstance(task, dict) and task.get("name") == task_name:
            return task[module_key]
    raise AssertionError(f"no task named {task_name!r} — this guard is pinned to the wrong name")


def _role_site() -> _Site:
    tasks = yaml.safe_load(_ROLE_TASKS.read_text(encoding="utf-8"))
    task = _pip_task_from_task_list(tasks, _ROLE_TASK_NAME, "ansible.builtin.pip")
    extra_args = " ".join(str(task.get("extra_args", "")).split())
    return _Site(label=f"npu-worker role ({_ROLE_TASKS.name})", packages=list(task["name"]), extra_args=extra_args)


def _playbook_site() -> _Site:
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    task = None
    for play in plays or []:
        try:
            task = _pip_task_from_task_list((play or {}).get("tasks", []), _PLAYBOOK_TASK_NAME, "pip")
            break
        except AssertionError:
            continue
    assert (
        task is not None
    ), f"no task named {_PLAYBOOK_TASK_NAME!r} in any play — this guard is pinned to the wrong name"
    extra_args = " ".join(str(task.get("extra_args", "")).split())
    return _Site(
        label=f"deploy-native-services.yml ({_PLAYBOOK.name})", packages=list(task["name"]), extra_args=extra_args
    )


def _requirements_file_site() -> _Site:
    lines = [line.strip() for line in _DOCKER_REQUIREMENTS.read_text(encoding="utf-8").splitlines()]
    constraint_lines = [line for line in lines if line.startswith("-c")]
    package_lines = [
        line.split("#", 1)[0].strip()
        for line in lines
        if line and not line.startswith("#") and not line.startswith("-c") and not line.startswith("-e")
    ]
    return _Site(
        label=f"requirements-npu.txt ({_DOCKER_REQUIREMENTS.name})",
        packages=[line for line in package_lines if line],
        extra_args=" ".join(constraint_lines),
    )


_SITES = {
    "role": _role_site,
    "playbook": _playbook_site,
    "requirements-npu.txt": _requirements_file_site,
}


def _ssot_openvino_floor() -> str:
    """The `openvino>=X` floor declared by the worker's own requirements.txt."""
    for line in _SSOT_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*openvino\s*>=\s*([0-9][0-9.]*)", line)
        if match:
            return match.group(1)
    raise AssertionError("no `openvino>=` floor in the SSOT requirements — this guard is pinned to the wrong file")


def test_the_sources_this_guard_reads_are_present():
    """Every half must parse, or every rule below is vacuous."""
    for site_name, site_factory in _SITES.items():
        site = site_factory()
        assert site.packages, f"{site_name}: installs nothing"
    assert _ssot_openvino_floor(), "no floor derived from the SSOT"


@pytest.mark.parametrize("site_name", list(_SITES))
def test_the_deprecated_meta_package_is_not_installed(site_name: str):
    """`openvino-dev` has no release compatible with openvino 2026.x.

    Asserted on the parsed package names rather than the file text: a comment
    naming the package would match a substring search over the source and pass
    regardless of what is installed. That is not hypothetical — it is how the
    first version of this check (for the role site) failed.
    """
    site = _SITES[site_name]()
    offenders = [name for name in site.packages if _bare_name(name) == "openvino-dev"]

    assert not offenders, (
        f"{site.label} installs {offenders} — pip backtracks to a numpy with no cp314 wheel "
        "and provisioning dies in an sdist build (#14447, #14452, #14453)"
    )


@pytest.mark.parametrize("site_name", list(_SITES))
def test_the_floor_is_not_below_the_ssot(site_name: str):
    """A lower floor lets the resolver walk backwards into pre-cp314 releases.

    This is what made the openvino-dev conflict fatal rather than merely
    unsatisfiable: with a floor below the SSOT's there was an older openvino to
    retreat to.
    """
    site = _SITES[site_name]()
    specs = [name for name in site.packages if _bare_name(name) == "openvino"]
    assert specs, f"{site.label}: no longer installs openvino at all"

    ssot_floor = _ssot_openvino_floor()
    for spec in specs:
        match = re.search(r">=\s*([0-9][0-9.]*)", spec)
        assert match, f"{site.label}: {spec!r} has no lower bound, so pip may resolve any older release"
        assert _version_tuple(match.group(1)) >= _version_tuple(ssot_floor), (
            f"{site.label} pins openvino>={match.group(1)} while {_SSOT_REQUIREMENTS.name} "
            f"declares >={ssot_floor} — this site has drifted below the SSOT (#14447, #14452, #14453)"
        )


@pytest.mark.parametrize("site_name", list(_SITES))
def test_the_shared_constraints_are_applied(site_name: str):
    """Without them, any dependency can drag numpy below its pinned floor.

    `constraints/shared.txt` is what keeps numpy on 2.x; bypassing it entirely
    is why a transitive pin could reach 1.25.2.
    """
    site = _SITES[site_name]()

    assert "constraints/shared.txt" in site.extra_args, (
        f"{site.label} does not apply constraints/shared.txt, so a transitive dependency can "
        "drag numpy below its floor and force an unbuildable sdist (#14447, #14452, #14453)"
    )
    assert (
        "-c" in site.extra_args
    ), f"{site.label}: constraints/shared.txt is referenced but not passed as a `-c` constraints file"
