# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Exactly one role may write autobot-chromadb.service (#13870).

Two ansible roles each shipped a template with the SAME unit name and different
`ExecStart` paths, and both wrote `/etc/systemd/system/autobot-chromadb.service`
unconditionally. Whichever role ran last won, so the deployed binary path, the
Description and the restart policy all flipped with run order.

Observed live during the #4090 investigation: a self-update applied the redis
role, which rewrote the unit underneath a running deployment and pointed it at a
different venv. #4090's outage was an `ExecStart` naming a venv that had no
chromadb in it — which template was in force decided whether the box worked, and
nothing in the deploy made that choice visible or deliberate.

Both roles are legitimate: they install chromadb for different topologies. The
defect is that ownership was implicit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
_UNIT_DEST = "/etc/systemd/system/autobot-chromadb.service"
_ROLES = ("ai-stack", "redis")


def _iter_tasks(doc):
    """Yield every task mapping in a playbook or task file."""
    if isinstance(doc, list):
        for item in doc:
            if isinstance(item, dict):
                if any(k in item for k in ("tasks", "pre_tasks", "post_tasks", "handlers")):
                    for key in ("tasks", "pre_tasks", "post_tasks", "handlers"):
                        for task in item.get(key) or []:
                            if isinstance(task, dict):
                                yield task
                else:
                    yield item


def _template(role: str) -> Path:
    return _ANSIBLE / "roles" / role / "templates" / "autobot-chromadb.service.j2"


def _tasks_text(role: str) -> str:
    return (_ANSIBLE / "roles" / role / "tasks" / "code_only.yml").read_text(encoding="utf-8")


def test_both_roles_still_ship_a_template():
    """Guard the guard: if either template is renamed, every assertion below
    would pass against nothing."""
    for role in _ROLES:
        assert _template(role).is_file(), f"{role} no longer ships the unit template"


@pytest.mark.parametrize("role", _ROLES)
def test_the_unit_task_is_gated_on_ownership(role: str):
    """Both wrote the unit unconditionally — that is the defect."""
    text = _tasks_text(role)
    assert _UNIT_DEST in text, f"{role} no longer deploys the unit — this guard matches nothing"

    tasks = yaml.safe_load(text)
    deploying = [
        t for t in tasks if isinstance(t, dict) and (t.get("ansible.builtin.template") or {}).get("dest") == _UNIT_DEST
    ]
    assert len(deploying) == 1, f"{role} has {len(deploying)} tasks writing the unit"
    condition = deploying[0].get("when")
    assert condition, f"{role} writes {_UNIT_DEST} unconditionally — run order decides the ExecStart"
    assert "chromadb_service_owner" in str(condition), f"{role}'s gate does not reference the ownership variable"


@pytest.mark.parametrize("role", _ROLES)
def test_each_role_declares_a_default_owner(role: str):
    defaults = yaml.safe_load((_ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert "chromadb_service_owner" in defaults, f"{role} has no chromadb_service_owner default"
    assert defaults["chromadb_service_owner"] in _ROLES


def test_the_roles_do_not_share_one_default():
    """They must DISAGREE — each defaults to its own name.

    The first version asserted the opposite, and that is what produced the
    review's headline defect: with both roles defaulting to "redis", every
    topology that runs ai-stack without redis skipped the template task and
    deployed no unit at all. Five of six entry points, including the updater's.
    A default that is the role's own name always writes something.
    """
    values = {
        role: yaml.safe_load((_ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8"))[
            "chromadb_service_owner"
        ]
        for role in _ROLES
    }
    assert values == {role: role for role in _ROLES}, f"defaults must be self-named, got {values}"


def test_the_ai_stack_only_play_still_resolves_an_owner():
    """setup-ai-stack.yml needs no override now that the role default is
    self-named — and it must not have one.

    The first version added a SECOND `vars:` key to a play that already had one.
    YAML keeps the last, so the original seven variables were silently
    discarded and the play died on its first task with `'chromadb_port' is
    undefined`. `yaml.safe_load` returns the surviving duplicate, so the old
    assertion passed against a play that could not run — an empty result reading
    as a clean one.
    """

    class _NoDup(yaml.SafeLoader):
        pass

    def _no_duplicates(loader, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            assert key not in mapping, f"duplicate key in setup-ai-stack.yml: {key}"
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    _NoDup.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)
    play = yaml.load((_ANSIBLE / "setup-ai-stack.yml").read_text(encoding="utf-8"), _NoDup)[0]

    roles = {r["role"] if isinstance(r, dict) else r for r in play.get("roles", [])}
    assert "ai-stack" in roles and "redis" not in roles, "topology changed — revisit the ownership default"
    # The variables the play's own pre_tasks reference must survive.
    assert "chromadb_port" in play.get("vars", {}), "the play's original vars block was discarded"


def test_the_restart_policy_does_not_depend_on_which_role_won():
    """They differed — `always` vs `on-failure` — so the unit's FAILURE
    behaviour changed with role order, not just its path. #4090 was precisely
    about a unit restarting forever instead of reaching `failed`."""
    policies = {}
    for role in _ROLES:
        text = _template(role).read_text(encoding="utf-8")
        found = re.findall(r"^Restart=(\S+)", text, re.MULTILINE)
        assert found, f"{role}'s unit declares no Restart policy"
        policies[role] = found[0]
    assert len(set(policies.values())) == 1, f"restart policy differs between roles: {policies}"


def test_both_units_keep_the_4090_start_limit():
    """#4090: without these a unit whose ExecStart can never succeed restarts
    forever and never reaches `failed`. Both templates must keep them.

    Anchored to line starts. The first version used unanchored `in` checks,
    which matched the templates' own explanatory comment
    ("DefaultStartLimitIntervalSec=10s with DefaultStartLimitBurst=5") — so
    deleting both real directives left the test green. Verified: it now fails
    when either is removed.
    """
    for role in _ROLES:
        text = _template(role).read_text(encoding="utf-8")
        assert re.search(r"^StartLimitIntervalSec=", text, re.MULTILINE), f"{role} lost StartLimitIntervalSec (#4090)"
        assert re.search(r"^StartLimitBurst=", text, re.MULTILINE), f"{role} lost StartLimitBurst (#4090)"


def test_every_unit_writer_in_the_tree_is_gated():
    """The invariant, not the fix.

    The first version of this file checked one `code_only.yml` per role. That
    scope is why the review found five entry points deploying no unit: a guard
    that asserts the shape of the change cannot notice the paths the change
    missed.
    """
    ungated: list[str] = []
    for task_file in _ANSIBLE.rglob("*.yml"):
        try:
            docs = list(yaml.safe_load_all(task_file.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue
        for doc in docs:
            for task in _iter_tasks(doc):
                module = task.get("ansible.builtin.template") or task.get("template") or {}
                if not isinstance(module, dict) or module.get("dest") != _UNIT_DEST:
                    continue
                if "chromadb_service_owner" not in str(task.get("when", "")):
                    ungated.append(f"{task_file.relative_to(_ANSIBLE)}: {task.get('name')}")
    assert not ungated, "tasks writing the chromadb unit without an ownership gate: " + "; ".join(ungated)


def test_every_ai_stack_entry_point_resolves_to_a_writer():
    """A topology that applies ai-stack without redis must still get a unit.

    A shared default of one role's name meant five of six entry points —
    including the updater's own path — silently deployed nothing, which the
    PR's own comment had already identified as worse than the bug being fixed.
    The floor is now each role's own name, so a single-role topology always
    writes.
    """
    for role in _ROLES:
        defaults = yaml.safe_load((_ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8"))
        assert defaults["chromadb_service_owner"] == role, (
            f"{role}'s default must be its own name — a shared default makes every "
            "single-role topology deploy no unit at all"
        )


def test_the_combined_host_owner_is_derived_where_both_roles_can_run():
    """Both places that carry the role_*_active facts must agree, or a run that
    loads one and not the other resolves differently."""
    for rel in ("inventory/group_vars/all.yml", "playbooks/vars/role_active_facts.yml"):
        text = (_ANSIBLE / rel).read_text(encoding="utf-8")
        assert "chromadb_service_owner" in text, f"{rel} does not derive the owner"
        assert (
            "role_ai_stack_active" in text or "role_redis_active" in text
        ), f"{rel} does not derive the owner from a role_*_active fact"


def test_the_combined_host_keeps_todays_data_path():
    """ai-stack must win a combined host, because that is what wins TODAY.

    The old run order put ai-stack last (deploy.yml applies redis before
    ai-stack; the fleet play runs redis in phase 3 and ai-stack in 5a), so the
    live ExecStart --path is ai-stack's. Handing ownership to redis relocates
    the vector store, and chroma comes up healthy against an empty directory —
    the knowledge base would read as empty with no error anywhere. Making
    ownership deterministic must not smuggle in a data move.
    """
    for rel in ("inventory/group_vars/all.yml", "playbooks/vars/role_active_facts.yml"):
        text = (_ANSIBLE / rel).read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("chromadb_service_owner:"))
        assert "'ai-stack' if" in line, (
            f"{rel} hands a combined host to redis — that relocates the chroma data "
            "directory silently (#13870, open decision)"
        )
