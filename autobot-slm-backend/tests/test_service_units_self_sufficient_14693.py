# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""service_units.yml must not depend on its caller for privilege (#14693).

The file holds the SLM backend systemd unit definition. It was written for one
caller -- `slm_manager/tasks/main.yml`, which includes it from an escalating
context -- and #14668 added a second, the Play 1 include in
`update-all-nodes.yml`. No play in that playbook sets a play-level `become`;
every task declares its own. The include did not, so the template ran
unprivileged and died with "Destination /etc/systemd/system not writable".

That aborted Play 1 before the SLM restart, which meant the self-update never
restarted the service, the update-all resume hook never ran, and the whole job
wedged (#14683). It also meant the unit refresh that #14624/#14668 exist to
perform had never once run on the self-update path.

The playbook parses fine either way, so only a live run exposed it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_SERVICE_UNITS = _ANSIBLE / "roles" / "slm_manager" / "tasks" / "service_units.yml"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"


def _load(path: Path):
    assert path.is_file(), f"file under test is missing: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_service_unit_task_escalates() -> None:
    """The regression: these tasks write systemd state and need root."""
    tasks = _load(_SERVICE_UNITS)
    assert tasks, "service_units.yml defines no tasks"
    missing = [t.get("name", "<unnamed>") for t in tasks if t.get("become") is not True]
    assert not missing, (
        "these tasks write systemd state but rely on the caller to escalate, "
        f"which is what broke on the self-update path: {missing}"
    )


def test_the_playbook_still_supplies_no_play_level_become() -> None:
    """Why the task file has to carry it itself.

    If a play ever sets `become` for the whole play, the reasoning above changes
    and this guard should be revisited deliberately rather than silently.
    """
    plays = _load(_PLAYBOOK)
    escalating = [p.get("name", "<unnamed>") for p in plays if p.get("become") is True]
    assert not escalating, (
        "a play now escalates for every task; service_units.yml no longer needs "
        f"to be self-sufficient for this caller — revisit #14693: {escalating}"
    )


def test_play_one_still_includes_the_shared_task_file() -> None:
    """The caller that exposed the defect must stay wired.

    Without this, deleting the include would turn both tests above green while
    reintroducing the stale-unit drift #14624 closed.
    """
    plays = _load(_PLAYBOOK)
    includes = [
        task
        for play in plays
        for task in (play.get("tasks") or [])
        if (task.get("ansible.builtin.include_role") or {}).get("tasks_from") == "service_units.yml"
    ]
    assert includes, "no play includes service_units.yml — the self-update path renders no unit again"
