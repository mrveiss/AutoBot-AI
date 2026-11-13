# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The one finder for "this ansible task restarts unit X" (#20772, #21334).

A restart is either a direct ``systemd: state: restarted`` task or an include of the shared
``_shared/tasks/restart_unit.yml`` with the unit in its ``restart_unit_name`` var. Every guard
that locates a restart reads it through here, so a change to the shape is made once.
"""

from __future__ import annotations

SHARED_SUFFIX = "_shared/tasks/restart_unit.yml"


def systemd_spec(task: dict) -> dict | None:
    """The task's ``systemd`` argument mapping, else None."""
    spec = task.get("systemd") or task.get("ansible.builtin.systemd")
    return spec if isinstance(spec, dict) else None


def is_direct_restart(task: dict) -> bool:
    """A ``systemd: state: restarted`` task (the shape the shared task file replaced)."""
    spec = systemd_spec(task)
    return spec is not None and spec.get("state") == "restarted"


def shared_include(task: dict) -> object | None:
    """The include argument of a task that includes the shared restart file, else None."""
    inc = task.get("ansible.builtin.include_tasks") or task.get("include_tasks")
    target = inc.get("file") if isinstance(inc, dict) else inc
    return inc if isinstance(target, str) and target.endswith(SHARED_SUFFIX) else None


def shared_restart_vars(task: dict) -> dict | None:
    """The vars of a shared-restart include, else None."""
    return (task.get("vars") or {}) if shared_include(task) is not None else None


def restarted_unit(task: dict) -> str | None:
    """The unit name the task restarts (either shape), else None."""
    if is_direct_restart(task):
        return str((systemd_spec(task) or {}).get("name", ""))
    shared = shared_restart_vars(task)
    return None if shared is None else str(shared.get("restart_unit_name", ""))


def restarts_unit(task: dict, name: str | None = None) -> bool:
    """True if the task restarts ``name`` (any unit when None)."""
    unit = restarted_unit(task)
    return unit is not None and name in (None, unit)
