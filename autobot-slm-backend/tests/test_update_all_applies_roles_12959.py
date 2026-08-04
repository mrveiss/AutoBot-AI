# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: the builtin updater must APPLY the roles that own deployed files (#12959).

`update-all-nodes.yml` is the playbook behind code-sync / self-update — the only
updater a GUI user can reach. It deploys component *code* with inline tasks, but
the systemd units, env files and credential stores those components run under are
rendered from **role-owned templates**. A role the playbook never applies cannot
deliver a change to any of them:

    ansible.builtin.include_role:
      name: backend
      tasks_from: env_only        # ... and nothing else, originally

So a fix that lands in a role was inert on every host updated through the builtin
path. The merge was green, the issue got closed, `code_source` carried the
change, and the host never received it. Four confirmed instances: #12777
(faulthandler, `roles/backend/templates/`), #12886 (TTS worker,
`roles/tts-worker`), #12907 (credential consolidation, `roles/postgresql`), and
#12959's own report. The failure is silent, which is what makes it expensive —
nothing distinguishes "delivered" from "merged but never applied".

**Delivery is via targeted task files, not whole-role application.** Applying a
role in full would re-run its provisioning half on every update — apt, venv
creation, service accounts, gated model downloads — which is slow, needs network,
and can break a box that is already correctly installed. The contract is instead
that every role owning deployed artifacts exposes a code/config-only task file
(`env_only`, `unit_only`, `code_only`, `credentials_reconcile`) which the updater
applies, and which contains no provisioning. One implementation, two callers.

`test_every_managed_component_has_an_application_path` stays
``xfail(strict=True)`` while four components still have none: it keeps the suite
green, and the moment the gap closes it XPASSes — which strict xfail reports as a
FAILURE, forcing whoever fixed it to delete the marker. A baseline would instead
quietly absorb the fix and keep claiming the problem is still there (the #12894
lesson).
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

#: Components with a delivery path today. Each entry is a regression guard: the
#: named task file was added *because* a merged fix failed to reach a host.
DELIVERED = {
    "backend": {"env_only", "unit_only"},  # #12871, #12777
    "tts-worker": {"code_only"},  # #12886
    "postgresql": {"credentials_reconcile"},  # #12907
}

#: Task-name substrings that mean provisioning. None may appear in a task file
#: the updater applies — that work must not re-run on an installed box.
_PROVISIONING_MARKERS = ("venv", "pip install", "pre-download", "service account", "apt")


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

    ``None`` means the role is applied in full — which the updater deliberately
    never does, since that would drag provisioning onto the update path.
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


@pytest.mark.parametrize("component,task_files", sorted(DELIVERED.items()))
def test_delivered_components_keep_their_application_path(component, task_files):
    """A component that gained a delivery path must never silently lose it.

    Each of these exists because a merged fix did not reach a host. Dropping the
    include re-opens exactly that issue, with no visible symptom until someone
    re-diagnoses it on a live box weeks later.
    """
    role = MANAGED_COMPONENT_ROLES[component]
    applied = applied_roles().get(role, set())

    missing = task_files - applied
    assert not missing, (
        f"{component}: update-all-nodes.yml no longer applies roles/{role} "
        f"tasks_from={sorted(missing)} — changes to those files become inert on "
        f"every host again (#12959). Currently applied: {sorted(str(a) for a in applied)}"
    )


@pytest.mark.parametrize("component,task_files", sorted(DELIVERED.items()))
def test_applied_task_files_exist_and_carry_no_provisioning(component, task_files):
    """An include pointing at a missing file breaks the update on the host.

    And a task file that re-provisions turns every self-update into a reinstall,
    which is why delivery is split out of ``main.yml`` rather than applied whole.
    """
    role = MANAGED_COMPONENT_ROLES[component]

    for name in sorted(task_files):
        path = _ROLES_DIR / role / "tasks" / f"{name}.yml"
        assert path.is_file(), f"{component}: include_role tasks_from={name} has no {path}"

        tasks = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        names = " ".join(str(t.get("name", "")) for t in tasks if isinstance(t, dict)).lower()
        for marker in _PROVISIONING_MARKERS:
            assert marker not in names, (
                f"{component}/{name}.yml: provisioning task ({marker!r}) leaked onto "
                "the update path — it must stay in main.yml"
            )


@pytest.mark.xfail(
    strict=True,
    reason="#13460: ai-stack, npu-worker, frontend and browser own systemd units and env "
    "templates but expose no code/config-only task file, so a fix in any of them is still "
    "inert on hosts (#12959). When all four gain one this XPASSes — delete this marker then.",
)
def test_every_managed_component_has_an_application_path():
    """Every managed component's role must be reachable from the updater.

    ``tasks_from`` is the intended shape — full application would re-run
    provisioning. What is asserted here is only that *some* application exists.
    """
    applied = applied_roles()
    undelivered = [
        f"{component}: roles/{role} is NEVER applied"
        for component, role in sorted(MANAGED_COMPONENT_ROLES.items())
        if role not in applied
    ]

    assert not undelivered, (
        "Roles whose changes cannot reach a host through the builtin updater "
        "(#12959) — a fix merged into any of these is inert:\n  " + "\n  ".join(undelivered)
    )


def test_undelivered_roles_are_reported_for_visibility(capsys):
    """Always print the current delivery gap, so CI logs carry it while xfail hides the failure."""
    applied = applied_roles()
    gap = [
        f"{c}: roles/{r} NEVER applied"
        for c, r in sorted(MANAGED_COMPONENT_ROLES.items())
        if r not in applied
    ]
    print("\n#12959 delivery gap — roles the builtin updater cannot deliver a change through:")
    for line in gap:
        print(f"  {line}")

    # Not an assertion about the gap's size — only that the report ran and the
    # playbook still applies *something*, so a refactor cannot silently empty it.
    assert applied, "update-all-nodes.yml applies no roles at all"
