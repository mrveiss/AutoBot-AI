# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: the builtin updater must APPLY the roles it deploys (#12959).

`update-all-nodes.yml` is the playbook behind code-sync / self-update — the only
updater a GUI user can reach. It deploys components with inline tasks and
applies exactly one role, and only a single task file of it:

    ansible.builtin.include_role:
      name: backend
      tasks_from: env_only

So **any fix that lands in an Ansible role is inert on every host updated
through the builtin path**. The merge is green, the issue gets closed,
`code_source` carries the change, and the host never receives it. Four
confirmed instances: #12777 (faulthandler, `roles/backend/templates/`), #12886
(TTS worker, `roles/tts-worker`), #12907 (credential consolidation,
`roles/postgresql`), and #12959's own report.

The failure is silent, which is what makes it expensive: nothing distinguishes
"delivered" from "merged but never applied". This test makes it loud.

It is marked ``xfail(strict=True)`` rather than baselined: while the gap exists
the suite stays green, and the moment the updater applies these roles the test
XPASSes — which strict xfail reports as a FAILURE, forcing whoever fixed it to
delete the marker. A baseline would instead quietly absorb the fix and keep
claiming the problem is still there (the #12894 lesson).
"""

import pathlib

import pytest
import yaml

_ANSIBLE = pathlib.Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_ROLES_DIR = _ANSIBLE / "roles"

#: Components the updater deploys, mapped to the role that owns their real
#: deployment logic (unit files, templates, credentials, worker config).
#: A component here whose role is never applied receives code but no role
#: changes — the #12959 failure.
MANAGED_COMPONENT_ROLES = {
    "backend": "backend",
    "ai-stack": "ai-stack",
    "npu-worker": "npu-worker",
    "frontend": "frontend",
    "browser": "browser",
    "tts-worker": "tts-worker",
    "postgresql": "postgresql",
}


def _iter_tasks(node):
    """Yield every mapping in the playbook, at any nesting depth."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_tasks(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_tasks(item)


def applied_roles() -> dict[str, set[str | None]]:
    """Map each role the playbook applies to the ``tasks_from`` values used.

    ``None`` means the role is applied in full. A role that only ever appears
    with a ``tasks_from`` delivers just that task file — which is how `backend`
    ships `env_only` and nothing else.
    """
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    applied: dict[str, set[str | None]] = {}

    for task in _iter_tasks(playbook):
        include = task.get("ansible.builtin.include_role") or task.get("include_role")
        if isinstance(include, dict) and include.get("name"):
            applied.setdefault(include["name"], set()).add(include.get("tasks_from"))
        # A bare `roles:` list on a play applies each role in full.
        for entry in task.get("roles") or []:
            name = entry.get("role") or entry.get("name") if isinstance(entry, dict) else entry
            if name:
                applied.setdefault(name, set()).add(None)

    return applied


def test_playbook_is_parseable_and_still_the_updater():
    """Fail loudly if the playbook moved, rather than vacuously passing."""
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} not found — did the updater move?"
    assert yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8")), "playbook parsed empty"


@pytest.mark.parametrize("component,role", sorted(MANAGED_COMPONENT_ROLES.items()))
def test_managed_component_role_exists(component, role):
    """The role that owns each managed component's deployment must exist."""
    assert (_ROLES_DIR / role).is_dir(), f"{component}: roles/{role} missing"


@pytest.mark.xfail(
    strict=True,
    reason="#12959: the updater applies only backend/env_only, so role changes are inert on hosts. "
    "When the inline tasks become role applications this XPASSes — delete this marker then.",
)
def test_updater_applies_every_managed_role_in_full():
    """Every managed component's role must be applied, and applied in full.

    Applying with ``tasks_from`` is not delivery: `backend` is applied that way
    today and still never receives its unit-file template (#12777).
    """
    applied = applied_roles()
    undelivered = []

    for component, role in sorted(MANAGED_COMPONENT_ROLES.items()):
        if role not in applied:
            undelivered.append(f"{component}: roles/{role} is NEVER applied")
        elif None not in applied[role]:
            partial = ", ".join(sorted(str(t) for t in applied[role]))
            undelivered.append(f"{component}: roles/{role} applied only via tasks_from={partial}")

    assert not undelivered, (
        "Roles whose changes cannot reach a host through the builtin updater "
        "(#12959) — a fix merged into any of these is inert:\n  " + "\n  ".join(undelivered)
    )


def test_undelivered_roles_are_reported_for_visibility(capsys):
    """Always print the current delivery gap, so CI logs carry it while xfail hides the failure."""
    applied = applied_roles()
    gap = [
        f"{c}: roles/{r} " + ("NEVER applied" if r not in applied else f"partial {sorted(str(t) for t in applied[r])}")
        for c, r in sorted(MANAGED_COMPONENT_ROLES.items())
        if r not in applied or None not in applied[r]
    ]
    print("\n#12959 delivery gap — roles the builtin updater does not apply in full:")
    for line in gap:
        print(f"  {line}")

    # Not an assertion about the gap's size — only that the report ran and the
    # playbook still applies *something*, so a refactor cannot silently empty it.
    assert applied, "update-all-nodes.yml applies no roles at all"
