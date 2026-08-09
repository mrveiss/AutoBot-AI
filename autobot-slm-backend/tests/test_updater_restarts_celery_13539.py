# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater must restart celery, not only the backend (#13539).

``update-all-nodes.yml`` synced the backend tree and restarted
``autobot-backend`` — and left ``autobot-celery`` / ``autobot-celery-beat``
running whatever they had imported at their last start. Measured on a live host,
celery ran **7 days** behind the deployed code across four successful updates.

The failure that surfaces is misleading. Python caches modules in ``sys.modules``,
so a worker started before a symbol existed keeps a module object without it. Any
task that lazily imports a consumer of that symbol raises::

    cannot import name 'is_admin_role' from 'autobot_shared.auth.permissions'
    (/opt/autobot/autobot-backend/autobot_shared/auth/permissions.py)

pointing at a file that visibly *does* contain it — which sends the reader toward
packaging or symlinks rather than process age.

The role is not at fault: ``roles/backend/handlers/main.yml`` defines
``restart celery`` and ``restart celery beat``, and ``tasks/main.yml`` notifies
them. The updater simply never includes ``main.yml`` — it applies
``env_only`` / ``unit_only`` / ``code_only``, none of which contains a single
``notify:``. The handlers are present, correct, and unreachable.

These tests pin both halves: that the restart exists on the update path, and that
it does not regress into a handler notify. The latter matters because #13143
tried exactly that and #13144 had to replace it — a handler fires only when its
task reports ``changed``, so once the synced file is already current the notify
never happens and the restart silently does not occur.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_HANDLERS = _ANSIBLE / "roles" / "backend" / "handlers" / "main.yml"
_TASKS = _ANSIBLE / "roles" / "backend" / "tasks"

#: Units that import the backend tree and therefore must be restarted with it.
_CELERY_UNITS = ("autobot-celery", "autobot-celery-beat")

#: Partial task files the updater applies via ``tasks_from:``.
_PARTIAL_TASK_FILES = ("env_only.yml", "unit_only.yml", "code_only.yml")


def _iter_mappings(node):
    """Yield every mapping in a parsed YAML document, depth first."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mappings(item)


def _playbook_tasks():
    docs = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    return list(_iter_mappings(docs))


def _systemd_restart_targets(tasks):
    """Return the service names every ``systemd: state=restarted`` task targets.

    Covers both the literal ``name:`` form and the ``loop`` form used for celery,
    where the name is templated from the loop item.
    """
    targets = set()
    for task in tasks:
        spec = task.get("systemd") or task.get("ansible.builtin.systemd")
        if not isinstance(spec, dict) or spec.get("state") != "restarted":
            continue
        name = spec.get("name", "")
        if "{{" in str(name):
            # Templated name — resolve from the loop this task iterates.
            loop = task.get("loop")
            if isinstance(loop, list):
                targets.update(str(entry) for entry in loop)
            elif isinstance(loop, str):
                targets.add(loop)
        else:
            targets.add(str(name))
    return targets


def _loop_literals(tasks):
    """Every literal string appearing in a ``loop:`` list anywhere in the play."""
    found = set()
    for task in tasks:
        loop = task.get("loop")
        if isinstance(loop, list):
            found.update(str(entry) for entry in loop if isinstance(entry, str))
    return found


def test_backend_restart_is_still_present():
    """Guard the baseline: the backend itself must still be restarted."""
    targets = _systemd_restart_targets(_playbook_tasks())
    assert "autobot-backend" in targets, (
        "update-all-nodes.yml no longer restarts autobot-backend. This test exists "
        "to stop the celery fix from displacing the restart it was modelled on."
    )


@pytest.mark.parametrize("unit", _CELERY_UNITS)
def test_updater_restarts_celery_units(unit):
    """Both celery units must be restarted on the update path (#13539).

    Accepts either a direct ``name:`` or a loop over the unit names, so the fix
    may be written as one looped task or two explicit ones.
    """
    tasks = _playbook_tasks()
    restarted = _systemd_restart_targets(tasks)
    if unit in restarted:
        return
    assert unit in _loop_literals(tasks), (
        f"{unit} is never restarted by update-all-nodes.yml. It imports the backend "
        f"tree this play syncs, so leaving it running serves pre-deploy modules "
        f"until someone restarts it by hand — the #13539 condition. Restart it "
        f"alongside autobot-backend."
    )


def test_celery_restart_is_not_left_to_a_handler_notify():
    """The restart must not regress into a ``notify:`` the updater cannot reach.

    The handlers exist and the updater never includes the task file that notifies
    them. Even if it did, a handler fires only on ``changed`` — so a host whose
    files are already current would skip the restart and reintroduce the bug in a
    form that only appears on *some* runs. #13143 attempted the handler route and
    #13144 replaced it for exactly this reason.
    """
    for name in _PARTIAL_TASK_FILES:
        path = _TASKS / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "notify:" not in text, (
            f"{name} now contains a `notify:`. The updater applies this file via "
            f"`tasks_from:`, and handlers only fire on `changed`, so a notify here "
            f"is not a reliable restart. Restart explicitly in the play instead."
        )


def test_celery_handlers_still_exist_for_full_role_runs():
    """A full ``main.yml`` run must keep its handler path.

    The explicit restart added for #13539 covers the *updater*. Provisioning runs
    that do include ``main.yml`` still rely on these handlers, so removing them
    while "cleaning up" would break the other path.
    """
    handlers = yaml.safe_load(_HANDLERS.read_text(encoding="utf-8")) or []
    handler_targets = _systemd_restart_targets(list(_iter_mappings(handlers)))
    for unit in _CELERY_UNITS:
        assert unit in handler_targets, (
            f"roles/backend/handlers/main.yml no longer restarts {unit}. Full role "
            f"runs depend on these handlers; the updater's explicit restart does "
            f"not replace them."
        )


def test_absent_celery_unit_is_reported_not_silently_skipped():
    """A host with no celery unit must say so rather than skip in silence.

    "celery was never restarted" is the exact condition this issue is about, so a
    guard that hides it would defeat the fix. The play must emit something when a
    unit is missing.
    """
    text = _PLAYBOOK.read_text(encoding="utf-8")
    assert "not installed on this host" in text, (
        "The celery restart guard skips missing units without reporting them. A "
        "silently skipped restart is indistinguishable from the #13539 bug."
    )
