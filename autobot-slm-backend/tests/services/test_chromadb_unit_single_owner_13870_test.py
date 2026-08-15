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


def test_the_combined_host_owner_is_derived_where_both_roles_can_run():
    """Both places that carry the role_*_active facts must agree, or a run that
    loads one and not the other resolves differently."""
    for rel in ("inventory/group_vars/all.yml", "playbooks/vars/role_active_facts.yml"):
        text = (_ANSIBLE / rel).read_text(encoding="utf-8")
        assert "chromadb_service_owner" in text, f"{rel} does not derive the owner"
        assert (
            "role_ai_stack_active" in text or "role_redis_active" in text
        ), f"{rel} does not derive the owner from a role_*_active fact"


def _directive(text: str, name: str) -> str | None:
    match = re.search(rf"^{name}=(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


@pytest.mark.parametrize("role", _ROLES)
def test_both_units_disable_chroma_telemetry(role: str):
    """Chroma's telemetry is ON by default and posts to an external endpoint.
    One unit opted out and the other did not, so whether this deployment phoned
    home depended on which ansible role ran last."""
    text = _template(role).read_text(encoding="utf-8")
    assert 'Environment="ANONYMIZED_TELEMETRY=FALSE"' in text, f"{role}'s chroma still reports telemetry externally"


@pytest.mark.parametrize("role", _ROLES)
def test_the_unit_writing_to_a_file_is_unbuffered(role: str):
    """`StandardOutput=append:` is a FILE, which is fully buffered rather than
    line-buffered — so without this the log an operator reads during an incident
    lags the incident by up to a buffer."""
    text = _template(role).read_text(encoding="utf-8")
    if "StandardOutput=append:" not in text:
        pytest.skip(f"{role} does not append to a file")
    assert 'Environment="PYTHONUNBUFFERED=1"' in text, f"{role} buffers chroma's diagnostics into a file"


def test_each_role_keeps_a_self_named_floor():
    """The floor is what a role resolves to when applied ALONE with no vars
    layer loaded — `setup_wizard._generate_dynamic_inventory()` writes a bare
    temp inventory with no group_vars sibling, so the "Setup AI Stack Node"
    action sees nothing but these defaults.

    A shared default of one role's name means that host deploys NO unit at all.
    Review caught that in #14055, and I re-created it here by moving both floors
    to "redis" while fixing the ownership question — which is one precedence
    level up and unaffected by the floor.
    """
    for role in _ROLES:
        defaults = yaml.safe_load((_ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8"))
        assert defaults["chromadb_service_owner"] == role, (
            f"{role}'s floor must be its own name — a shared floor makes a single-role "
            "topology with no vars layer deploy nothing"
        )


def test_the_migration_does_not_gate_on_an_empty_target():
    """An interrupted copy leaves the target non-empty. Gating the retry on
    "target is empty" would skip it forever and serve the partial store — the
    same silent-wrong-data class the migration exists to prevent, one step
    removed."""
    tasks = (_ANSIBLE / "roles" / "redis" / "tasks" / "chromadb_data_migration.yml").read_text(encoding="utf-8")
    assert ".migrated-from-legacy" in tasks, "completeness is not tracked by a marker"
    assert "_chroma_migration_ran: false" in tasks, (
        "the safety net must use an explicit boolean — a registered task in a SKIPPED block "
        "still yields a result dict, so `is defined` reads True when nothing ran"
    )
    block_gate = tasks.index('- name: "ChromaDB | Migrate the persist directory')
    gate_text = tasks[block_gate : block_gate + 700]
    assert (
        "_chroma_target_files | int == 0" not in gate_text
    ), "the migration gates on an empty target — an interrupted copy would never be retried"


def test_the_database_stack_owns_the_database():
    """ChromaDB is a database, so on a host running both roles the db stack owns
    its unit — and that is the only role that installs chromadb.

    Asserted on the DERIVATION, not on the role defaults. The defaults are a
    fail-safe floor for a role applied alone; the ownership decision is one
    precedence level up. Conflating the two is how I broke the ai-stack-only
    topology while fixing this.

    An earlier revision made ai-stack the owner on a combined host to avoid
    relocating the persist directory. That produced the #4090 outage live:
    ExecStart pointed at /opt/autobot/autobot-ai-stack/venv/bin/chroma, which
    does not exist, and the unit reached NRestarts=4399 while reporting
    `activating`.
    """
    for rel in ("inventory/group_vars/all.yml", "playbooks/vars/role_active_facts.yml"):
        line = next(
            ln
            for ln in (_ANSIBLE / rel).read_text(encoding="utf-8").splitlines()
            if ln.startswith("chromadb_service_owner:")
        )
        assert "'redis' if" in line, (
            f"{rel} does not hand a combined host to the db stack — the ai-stack venv " "has no chromadb installed"
        )

    deploy = (_ANSIBLE / "deploy.yml").read_text(encoding="utf-8")
    owner_line = next(ln for ln in deploy.splitlines() if "chromadb_service_owner:" in ln)
    assert "'redis' if" in owner_line, "deploy.yml still prefers ai-stack when both are requested"


def test_the_persist_directory_moves_with_the_service():
    """The store follows the database. The migration must exist and must refuse
    to leave the service pointed at an empty directory while the legacy path
    holds data — chroma starts happily on an empty store and the knowledge base
    simply reads as empty, with no error anywhere."""
    tasks = (_ANSIBLE / "roles" / "redis" / "tasks" / "chromadb_data_migration.yml").read_text(encoding="utf-8")
    assert "chromadb_legacy_data_dir" in tasks
    assert "assert" in tasks, "the migration has no guard against serving an empty store"

    code_only = (_ANSIBLE / "roles" / "redis" / "tasks" / "code_only.yml").read_text(encoding="utf-8")
    assert "chromadb_data_migration.yml" in code_only, "the migration is never included"
    assert code_only.index("chromadb_data_migration.yml") < code_only.index(
        _UNIT_DEST
    ), "the migration must run BEFORE the unit is deployed, or the service starts on the old path"


def test_the_marker_is_written_only_after_the_copy_is_verified():
    """Order is the entire guarantee, and nothing asserted it.

    Round-2 review swapped the assert and the marker-write and the suite stayed
    green. If the marker lands first, an incomplete copy is recorded as migrated
    — the block then skips forever and chroma serves a partial store, which is
    exactly the failure the marker was introduced to prevent.

    Checking the strings in isolation cannot see this: both are present either
    way. Only their relative position carries the meaning.
    """
    tasks = (_ANSIBLE / "roles" / "redis" / "tasks" / "chromadb_data_migration.yml").read_text(encoding="utf-8")
    verify_at = tasks.index("The copy must be complete before anything trusts it")
    marker_at = tasks.index("Mark the store migrated")
    assert verify_at < marker_at, (
        "the migration marker is written BEFORE the copy is verified — an incomplete "
        "copy would be recorded as migrated and never retried (#13870)"
    )

    copy_at = tasks.index("Copy the store to the db-stack path")
    assert copy_at < verify_at, "the verification must follow the copy it verifies"
