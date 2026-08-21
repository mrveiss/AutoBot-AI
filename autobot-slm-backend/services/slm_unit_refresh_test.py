# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The self-update path must refresh the systemd unit, not just the code (#14624).

A deployed SLM backend crash-looped for ~11 hours — uvicorn exiting 1 at import,
5658 restarts, API unreachable. The cause was a unit file dated two months
earlier that predated the `AUTOBOT_PROJECT_ROOT` line its template had carried
since #14575, so once `resolve_project_root` began raising rather than guessing
(#14544) the service could not start. Recovery needed root on the box, because
the code-sync and self-update endpoints live in the service that would not run.

The diagnosis that mattered came after the fix: a full self-update propagated
new code in 53 seconds and left the unit untouched. Play 1 of
`update-all-nodes.yml` deploys the backend by unarchive and deliberately does
not run the `slm_manager` role — the playbook says so itself, in the comment
above its duplicated marker-write.

So the unit definition now lives in one task file that both callers include,
and these rules pin that arrangement. A second copy of the template task would
pass a naive "does Play 1 render the unit" check while drifting from the role's
version, which is precisely the failure being fixed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parent.parent / "ansible"
_ROLE_TASKS = _ANSIBLE / "roles" / "slm_manager" / "tasks"
_SHARED_UNIT_TASKS = _ROLE_TASKS / "service_units.yml"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"


def _tasks(path: Path):
    """Every task in a file, including those nested in block/rescue/always."""

    def walk(items):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            yield item
            for key in ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks"):
                if isinstance(item.get(key), list):
                    yield from walk(item[key])

    for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if isinstance(document, list):
            yield from walk(document)
        elif isinstance(document, dict):
            yield from walk([document])


def test_the_shared_unit_task_file_exists_and_renders_the_template():
    """The single definition both callers depend on."""
    assert _SHARED_UNIT_TASKS.is_file(), "service_units.yml is gone — the shared definition was removed"

    templated = [
        t
        for t in _tasks(_SHARED_UNIT_TASKS)
        if isinstance(t.get("ansible.builtin.template"), dict)
        and "autobot-slm-backend.service.j2" in str(t["ansible.builtin.template"].get("src", ""))
    ]

    assert templated, "service_units.yml no longer renders the backend unit template"


def test_the_self_update_play_refreshes_the_unit():
    """The #14624 regression: Play 1 deployed code and left the unit stale."""
    including = [
        t
        for t in _tasks(_PLAYBOOK)
        if isinstance(t.get("ansible.builtin.include_role"), dict)
        and t["ansible.builtin.include_role"].get("tasks_from") == "service_units.yml"
    ]

    assert including, (
        "update-all-nodes.yml no longer includes service_units.yml — the self-update path "
        "would deploy new code against a stale systemd unit again (#14624)"
    )


def test_the_playbook_does_not_carry_its_own_copy_of_the_unit_task():
    """A second copy is what drifts.

    The marker-write in this same play is exactly that mistake, duplicated from
    the role since #12223. Rendering the unit by a copied `template:` task would
    satisfy the rule above while reintroducing the divergence.
    """
    copies = [
        t
        for t in _tasks(_PLAYBOOK)
        if isinstance(t.get("ansible.builtin.template"), dict)
        and "autobot-slm-backend.service.j2" in str(t["ansible.builtin.template"].get("src", ""))
    ]

    assert not copies, (
        "the playbook renders the unit template directly instead of including the shared "
        "task file — that copy will drift from the role's (#14624)"
    )


def test_the_role_still_reaches_the_shared_file():
    """Extraction must not have orphaned it from a full provision."""
    main = _ROLE_TASKS / "main.yml"

    including = [
        t
        for t in _tasks(main)
        if str(t.get("ansible.builtin.include_tasks", "")).endswith("service_units.yml")
    ]

    assert including, "slm_manager/main.yml no longer includes service_units.yml — a full provision would skip the unit"


def test_the_unit_template_survives_a_caller_without_the_postgresql_role():
    """The include runs from a play that has not applied the postgresql role.

    `postgresql_credentials_dir` is defined in THAT role's defaults, so rendering
    from Play 1 would fail on an undefined variable. It resolved before only
    because the role happened to run alongside — a coincidence, not a contract.
    """
    template = (_ANSIBLE / "roles" / "slm_manager" / "templates" / "autobot-slm-backend.service.j2").read_text(
        encoding="utf-8"
    )

    for var in ("postgresql_credentials_dir", "postgresql_credentials_file"):
        for line in template.splitlines():
            if var in line:
                assert "default(" in line, f"{var} is referenced without a default; rendering from Play 1 would fail"
