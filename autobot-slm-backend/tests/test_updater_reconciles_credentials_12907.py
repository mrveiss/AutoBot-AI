# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater must reconcile the DB credential store (#12907, #12959).

#12907's fix — strip the pre-#12224 unmarked duplicate keys, retire the
superseded ``autobot-db-credentials.env`` — landed in
``roles/postgresql/tasks/databases.yml``. ``update-all-nodes.yml`` applies
neither that role nor an inline copy, so the fix was merged, the issue closed,
and five full self-update runs (``ok=108 changed=32``) left both credential
files byte-identical. The duplicate ``AUTOBOT_DB_PASSWORD`` that caused the
#12883 outage was still there afterwards.

These tests pin the three properties that close it:

1. the reconciliation is applied by the updater, for both credential prefixes;
2. it exists exactly once — extracted to its own task file and *included* by
   ``databases.yml``, not copied into the playbook, because inline-vs-role
   duplication is the root cause #12959 is about;
3. it is guarded, so a host whose canonical store has no managed block is left
   alone rather than stripped of every credential it has.

The companion guard ``test_update_all_applies_roles_12959.py`` still xfails
after this: ``tasks_from`` is partial application, and the architectural
question of applying roles in full is separate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_ROLE_TASKS = _ANSIBLE / "roles" / "postgresql" / "tasks"
_RECONCILE = _ROLE_TASKS / "credentials_reconcile.yml"
_DATABASES = _ROLE_TASKS / "databases.yml"

#: The awk program that strips unmarked duplicates. Distinctive enough that a
#: copy anywhere else in the tree is a real duplication, not a coincidence.
_STRIP_FINGERPRINT = 'dropped++; next'


def _iter_mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mappings(item)


def _reconcile_includes() -> list[dict]:
    """Every playbook task that applies the postgresql credential reconcile."""
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    found = []
    for task in _iter_mappings(playbook):
        inc = task.get("ansible.builtin.include_role") or task.get("include_role")
        if (
            isinstance(inc, dict)
            and inc.get("name") == "postgresql"
            and inc.get("tasks_from") == "credentials_reconcile"
        ):
            found.append(task)
    return found


def test_reconcile_task_file_exists():
    assert _RECONCILE.is_file(), (
        f"{_RECONCILE} missing — without it the #12907 fix has no application "
        "path that does not also run the whole postgresql role"
    )


def test_updater_applies_the_reconcile_for_both_prefixes():
    """db-credentials.env is shared by the SLM_ and AUTOBOT_ prefixes.

    Reconciling only one leaves the other's stale duplicates in place, and the
    SLM migration parse takes the *first* ``DATABASE_URL=`` match.
    """
    prefixes = {
        (task.get("vars") or {}).get("db_env_prefix") for task in _reconcile_includes()
    }
    assert {"SLM", "AUTOBOT"} <= prefixes, (
        "update-all-nodes.yml must apply roles/postgresql credentials_reconcile "
        f"for both prefixes; found {sorted(p for p in prefixes if p)}"
    )


def test_reconcile_runs_with_become():
    """/etc/autobot/db-credentials.env is root-owned, mode 0600.

    ``become`` is not a valid keyword on a dynamic ``include_role`` — ansible
    rejects the whole playbook — so privilege must be handed over via ``apply``.
    """
    for task in _reconcile_includes():
        inc = task.get("ansible.builtin.include_role") or task["include_role"]
        assert (inc.get("apply") or {}).get("become") is True, (
            f"{task.get('name')!r}: reconcile needs `apply: {{become: true}}`; "
            "a bare `become` on include_role breaks every self-update"
        )


def test_reconcile_is_defined_exactly_once():
    """The strip logic must not be copied into the playbook or the role's main flow.

    Two implementations of the same deploy step, free to drift, is precisely
    the #12959 failure mode.
    """
    tree = _ANSIBLE.parent.parent
    copies = [
        path
        for path in tree.rglob("*.yml")
        if "node_modules" not in path.parts and _STRIP_FINGERPRINT in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert copies == [_RECONCILE], (
        "the credential-strip logic must live only in "
        f"{_RECONCILE.name}; also found in {[str(p) for p in copies if p != _RECONCILE]}"
    )


def test_databases_yml_includes_rather_than_repeats_it():
    tasks = yaml.safe_load(_DATABASES.read_text(encoding="utf-8"))
    includes = [
        (t.get("ansible.builtin.include_tasks") or t.get("include_tasks")) for t in tasks
    ]
    assert "credentials_reconcile.yml" in includes, (
        "roles/postgresql/tasks/databases.yml must include credentials_reconcile.yml "
        "so provisioning and the updater share one implementation"
    )


def test_strip_is_guarded_on_the_managed_block_existing():
    """Unguarded, the strip would wipe every credential off a pre-#12224 host.

    The awk drops any ``PREFIX_*=`` assignment outside the managed markers. On a
    host that has no managed block at all, that is *every* assignment — the
    strip is only safe because ``databases.yml`` writes the block immediately
    before. Standalone application has no such guarantee.
    """
    tasks = yaml.safe_load(_RECONCILE.read_text(encoding="utf-8"))
    strip = next(t for t in tasks if "Strip pre-#12224" in t["name"])
    guard = strip.get("when")
    guard = [guard] if isinstance(guard, str) else list(guard or [])
    assert any("_cred_block_present" in str(c) for c in guard), (
        "the strip task must be conditional on the managed block being present; "
        f"found when={guard!r}"
    )


def test_updater_asserts_delivery_instead_of_reporting_success_blindly():
    """A green run that delivered nothing is the outcome #12959 is about."""
    text = _PLAYBOOK.read_text(encoding="utf-8")
    playbook = yaml.safe_load(text)
    asserts = [
        task
        for task in _iter_mappings(playbook)
        if (task.get("ansible.builtin.assert") or task.get("assert"))
        and "12959" in str(task.get("name", ""))
    ]
    assert asserts, "update-all-nodes.yml has no post-update delivery assertion (#12959)"

    covered = " ".join(
        str((t.get("ansible.builtin.assert") or t["assert"]).get("that")) for t in asserts
    )
    for invariant, issue in (
        ("faulthandler", "#12777"),
        ("dup_cred_keys", "#12907 Defect 1"),
        ("legacy_store", "#12907 Defect 2"),
    ):
        assert invariant in covered, f"no delivery assertion for {issue} ({invariant})"
