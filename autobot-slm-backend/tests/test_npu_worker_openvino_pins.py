# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The npu-worker role's inline package list must not contradict the SSOT (#14447).

The role installs OpenVINO from a list written into the task, not from
`autobot-npu-worker/requirements.txt`. The two drifted: the SSOT said
`openvino>=2026.3.0`, the role said `>=2024.0` and additionally pulled
`openvino-dev` -- a deprecated meta-package frozen at 2024.6.0 with no release
compatible with openvino 2026.x.

pip therefore backtracked through every openvino-dev version down to 2022.3.2,
each pinning numpy lower, until it reached numpy==1.25.2, which has no cp314
wheel. The sdist build failed with `Cannot import 'setuptools.build_meta'` --
an error that names the build backend and nothing else. Provisioning was dead
on the NPU worker with no indication of which requirement caused it.

The floor is read out of the SSOT rather than repeated here. A test that
hardcoded `2026.3.0` would go stale in exactly the way the role did.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ROLE_TASKS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "npu-worker" / "tasks" / "main.yml"
_SSOT_REQUIREMENTS = _REPO_ROOT / "autobot-npu-worker" / "requirements.txt"

_TASK_NAME = "Install OpenVINO and dependencies"


def _pip_task() -> dict:
    tasks = yaml.safe_load(_ROLE_TASKS.read_text(encoding="utf-8"))
    for task in tasks or []:
        if isinstance(task, dict) and task.get("name") == _TASK_NAME:
            return task["ansible.builtin.pip"]
    raise AssertionError(f"no task named {_TASK_NAME!r} — this guard is pinned to the wrong name")


def _packages() -> list[str]:
    return list(_pip_task()["name"])


def _version_tuple(spec: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", spec)[:3])


def _ssot_openvino_floor() -> str:
    """The `openvino>=X` floor declared by the worker's own requirements.txt."""
    for line in _SSOT_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*openvino\s*>=\s*([0-9][0-9.]*)", line)
        if match:
            return match.group(1)
    raise AssertionError("no `openvino>=` floor in the SSOT requirements — this guard is pinned to the wrong file")


def test_the_sources_this_guard_reads_are_present():
    """Both halves must parse, or every rule below is vacuous."""
    assert _packages(), "the pip task installs nothing"
    assert _ssot_openvino_floor(), "no floor derived from the SSOT"


def test_the_deprecated_meta_package_is_not_installed():
    """`openvino-dev` has no release compatible with openvino 2026.x.

    Asserted on the parsed package names rather than the file text: the comment
    above the task names the package, so a substring search over the source
    matches the explanation and passes regardless of what is installed. That is
    not hypothetical — it is how the first version of this check failed.
    """
    offenders = [name for name in _packages() if re.split(r"[<>=\[]", name)[0].strip() == "openvino-dev"]

    assert not offenders, (
        f"the role installs {offenders} — pip backtracks to a numpy with no cp314 wheel "
        "and provisioning dies in an sdist build (#14447)"
    )


def test_the_role_floor_is_not_below_the_ssot():
    """A lower floor lets the resolver walk backwards into pre-cp314 releases.

    This is what made the openvino-dev conflict fatal rather than merely
    unsatisfiable: with `>=2024.0` there was an older openvino to retreat to.
    """
    role_specs = [name for name in _packages() if re.split(r"[<>=\[]", name)[0].strip() == "openvino"]
    assert role_specs, "the role no longer installs openvino at all"

    ssot_floor = _ssot_openvino_floor()
    for spec in role_specs:
        match = re.search(r">=\s*([0-9][0-9.]*)", spec)
        assert match, f"{spec!r} has no lower bound, so pip may resolve any older release"
        assert _version_tuple(match.group(1)) >= _version_tuple(ssot_floor), (
            f"the role pins openvino>={match.group(1)} while {_SSOT_REQUIREMENTS.name} "
            f"declares >={ssot_floor} — the inline list has drifted below the SSOT (#14447)"
        )


def test_the_shared_constraints_are_applied():
    """Without them, any dependency can drag numpy below its pinned floor.

    `constraints/shared.txt` is what keeps numpy on 2.x; the inline pip call
    bypassed it entirely, which is why a transitive pin could reach 1.25.2.
    """
    extra_args = " ".join(str(_pip_task().get("extra_args", "")).split())

    assert "constraints/shared.txt" in extra_args, (
        "the OpenVINO install does not apply constraints/shared.txt, so a transitive "
        "dependency can pin numpy below its floor and force an unbuildable sdist (#14447)"
    )
    assert "-c " in extra_args, "constraints/shared.txt is referenced but not passed as a `-c` constraints file"
