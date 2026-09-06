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

#15823 then satisfied the escalation test below by putting `become: true` on an
`include_tasks`. Ansible rejects that at parse time -- "'become' is not a valid
attribute for a TaskInclude" -- which aborted the whole self-update play and
broke code-sync on the live host. The guard had demanded something invalid, so
the tests here now check both directions: every task that can escalate does, no
include pretends to, and the files they include are read rather than trusted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_SERVICE_UNITS = _ANSIBLE / "roles" / "slm_manager" / "tasks" / "service_units.yml"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_HANDLERS = _ANSIBLE / "roles" / "slm_manager" / "handlers" / "main.yml"


def _walk_tasks(container):
    """Yield tasks from a play or block, including nested ones.

    `tasks` alone is not enough: this playbook also uses `pre_tasks` and
    `block`, so a guard that reads only `tasks` reports "not found" when an
    include is merely moved -- a false alarm that looks exactly like real
    removal.
    """
    if isinstance(container, list):
        for item in container:
            yield from _walk_tasks(item)
        return
    if not isinstance(container, dict):
        return
    yield container
    for key in ("tasks", "pre_tasks", "post_tasks", "block", "rescue", "always"):
        if container.get(key):
            yield from _walk_tasks(container[key])


def _load(path: Path):
    assert path.is_file(), f"file under test is missing: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


_INCLUDE_KEYS = (
    "ansible.builtin.include_tasks",
    "include_tasks",
    "ansible.builtin.import_tasks",
    "import_tasks",
)


def _included_file(task):
    """The task file this task includes, or None if it is not an include.

    Ansible accepts both the bare-string form (`include_tasks: f.yml`) and the
    mapping form (`include_tasks: {file: f.yml}`). A guard that reads only the
    first treats the second as an ordinary task and demands `become` on it --
    which Ansible rejects at parse time. Reading both is what keeps this guard
    from asking for something invalid.
    """
    for key in _INCLUDE_KEYS:
        value = task.get(key)
        if not value:
            continue
        return value if isinstance(value, str) else value.get("file")
    return None


def _leaf_tasks(container, inherited=False):
    """Yield `(name, escalated)` for every leaf task, honouring inheritance.

    `become` on a block applies to every task inside it, so a child that does
    not set it is still privileged. A guard that reads tasks in isolation
    reports the children of an escalating block as violations, and gets
    "fixed" by pasting `become` onto each one -- noise that buries the real
    question. Only leaves are yielded: a block is not a thing that runs.
    """
    if isinstance(container, list):
        for item in container:
            yield from _leaf_tasks(item, inherited)
        return
    if not isinstance(container, dict):
        return
    escalated = inherited or container.get("become") is True
    children = [container[key] for key in ("block", "rescue", "always") if container.get(key)]
    if not children:
        yield container.get("name", "<unnamed>"), escalated
        return
    for child in children:
        yield from _leaf_tasks(child, escalated)


def test_every_service_unit_task_escalates() -> None:
    """The regression: these tasks write systemd state and need root."""
    tasks = _load(_SERVICE_UNITS)
    assert tasks, "service_units.yml defines no tasks"
    missing = [t.get("name", "<unnamed>") for t in tasks if _included_file(t) is None and t.get("become") is not True]
    assert not missing, (
        "these tasks write systemd state but rely on the caller to escalate, "
        f"which is what broke on the self-update path: {missing}"
    )


def test_no_service_unit_include_carries_become() -> None:
    """`become` on a TaskInclude is a parse-time error, not a stricter setting.

    Ansible rejects it outright -- "'become' is not a valid attribute for a
    TaskInclude" -- and rejects it while *parsing*, so it aborts the entire play
    before any task runs. #15823 added one here to satisfy the escalation test
    above, and took the self-update path down on the live host: code-sync failed
    at parse time and the operator saw a job that never progressed.

    This is the direction the escalation test structurally cannot express. That
    test asks "does every task escalate". This one asks "is escalation even
    legal here", and for an include the answer is no. A guard that only ever
    asks for *more* of a property cannot notice that the property is invalid.
    """
    offenders = [
        task.get("name", "<unnamed>")
        for task in _load(_SERVICE_UNITS)
        if _included_file(task) is not None and "become" in task
    ]
    assert not offenders, (
        "these tasks set `become` on an include, which Ansible rejects at parse "
        f"time and which aborts the whole play: {offenders}. Escalation belongs "
        "on the tasks inside the included file."
    )


def test_every_included_task_file_escalates_on_its_own() -> None:
    """Exempting includes is only safe because this reads what they include.

    Without this test the exemption in `test_every_service_unit_task_escalates`
    *is* the bypass: move privileged work into a separate file, include it, and
    nothing demands escalation anywhere -- the include is exempt for being an
    include, and the included file is never read. That is the #14693 defect with
    one more level of indirection, and it would pass every other test here.
    """
    includes = [
        (task.get("name", "<unnamed>"), _included_file(task))
        for task in _load(_SERVICE_UNITS)
        if _included_file(task) is not None
    ]
    assert includes, (
        "service_units.yml includes no task files, so this guard examined "
        "nothing. It is not passing -- it is vacuous. Delete it or fix the sweep."
    )

    reached, unescalated = 0, []
    for task_name, target in includes:
        path = _SERVICE_UNITS.parent / target
        assert path.is_file(), f"{task_name} includes {target}, which does not exist"
        leaves = list(_leaf_tasks(_load(path)))
        assert leaves, f"{target} defines no tasks, so {task_name} includes nothing"
        reached += len(leaves)
        unescalated += [f"{target}::{name}" for name, escalated in leaves if not escalated]

    assert not unescalated, (
        "these tasks run inside an included file without escalating, so the "
        f"include is a hole in the #14693 guarantee: {unescalated}"
    )
    assert reached >= len(includes), f"walked {reached} tasks across {len(includes)} includes"


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


def test_every_handler_escalates() -> None:
    """The handlers these tasks notify need root too.

    `restart slm backend` carries `failed_when: false`, so an unprivileged
    restart does not fail the play -- the service just never restarts and
    nothing says so. That is the same silent no-restart the wedge turns on.
    """
    handlers = _load(_HANDLERS)
    assert handlers, "no handlers defined"
    missing = [h.get("name", "<unnamed>") for h in handlers if h.get("become") is not True]
    assert not missing, f"these handlers perform privileged operations without escalating: {missing}"


def test_play_one_still_includes_the_shared_task_file() -> None:
    """The caller that exposed the defect must stay wired.

    Without this, deleting the include would turn both tests above green while
    reintroducing the stale-unit drift #14624 closed.
    """
    plays = _load(_PLAYBOOK)
    includes = [
        task
        for task in _walk_tasks(plays)
        if (
            (task.get("ansible.builtin.include_role") or task.get("include_role") or {}).get("tasks_from")
            == "service_units.yml"
        )
    ]
    assert includes, "no play includes service_units.yml — the self-update path renders no unit again"
