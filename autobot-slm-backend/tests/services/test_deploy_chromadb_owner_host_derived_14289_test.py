# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A single-role redeploy must not claim chromadb ownership from target_roles
(#14289).

Three code paths reach `ansible/deploy.yml`:

- `services/playbook_executor.py::execute_playbook` -- builds a temp inventory
  and symlinks `inventory/group_vars/` beside it, so `role_redis_active` /
  `role_ai_stack_active` resolve from `inventory/group_vars/all.yml`.
- `api/setup_wizard.py::_generate_dynamic_inventory` -- since #14287, also
  links `group_vars/` the same way.
- `services/deployment.py::_execute_ansible_playbook` -- runs
  `ansible-playbook ... -i {host},`. That `-i` value is a bare inline host
  string, not an inventory FILE, so Ansible's `group_vars/` auto-discovery
  (which resolves relative to the inventory file's directory) never fires on
  this path at all -- with or without #14287.

`deploy.yml` is the one file all three converge on, so it is the only place a
fix can be robust regardless of caller. The pre-fix bug was a play-level
`vars:` entry that recomputed `chromadb_service_owner` from `target_roles`
(what THIS run was asked to deploy) instead of the shared `role_redis_active`
/ `role_ai_stack_active` facts (what is actually installed on the host) --
Ansible play vars outrank `group_vars`, so a `target_roles=ai-stack` redeploy
against an already-combined host reclaimed the unit from redis on every run
(#4090's outage verbatim).

The invariant these guard: `deploy.yml` resolves ownership from host state,
and does so on its own -- no execution stack's inventory-linking behavior may
be a precondition for the answer being correct.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
_DEPLOY = _ANSIBLE / "deploy.yml"


def _deploy_play() -> dict:
    docs = yaml.safe_load(_DEPLOY.read_text(encoding="utf-8"))
    assert isinstance(docs, list) and docs, "deploy.yml did not parse to a play list"
    return docs[0]


def test_deploy_yml_loads_the_shared_role_active_facts():
    """`services/deployment.py` invokes deploy.yml with a bare `-i host,`
    inventory string, so group_vars auto-discovery can never supply
    role_redis_active/role_ai_stack_active on that path. Only an explicit
    `vars_files` load makes chromadb_service_owner resolve correctly there."""
    play = _deploy_play()
    vars_files = [str(v) for v in play.get("vars_files") or []]
    assert any(v.endswith("role_active_facts.yml") for v in vars_files), (
        "deploy.yml no longer loads playbooks/vars/role_active_facts.yml -- a caller with "
        "no group_vars sibling would see role_redis_active/role_ai_stack_active as undefined"
    )


def test_deploy_yml_does_not_re_derive_ownership_in_its_own_vars_block():
    """The #14289 regression itself: a play `vars:` entry for
    chromadb_service_owner outranks the correctly-derived facts, wherever they
    come from (group_vars or vars_files)."""
    play = _deploy_play()
    play_vars = play.get("vars") or {}
    assert "chromadb_service_owner" not in play_vars, (
        "deploy.yml re-derives chromadb_service_owner in its own play vars: block -- "
        "this always outranks the host-derived facts and was the #14289 bug"
    )


def test_no_chromadb_owner_derivation_anywhere_reads_target_roles_or_role_list():
    """The invariant, not today's specific spelling: a unit shared by two
    roles may only be claimed from facts ABOUT THE HOST
    (role_redis_active / role_ai_stack_active), never from target_roles or
    role_list -- the caller's list of roles to run THIS pass, which says
    nothing about what is already installed on the host.

    Scans every ansible YAML file rather than just deploy.yml, so a future
    reintroduction anywhere in the tree (a new playbook, a role default, a
    second override) is caught the same way.
    """
    offenders: list[str] = []
    for path in _ANSIBLE.rglob("*.yml"):
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.split("#", 1)[0]
            if "chromadb_service_owner" not in line or ":" not in line:
                continue
            key = line.split(":", 1)[0].strip()
            if key != "chromadb_service_owner":
                continue
            if re.search(r"\btarget_roles\b|\brole_list\b", line):
                offenders.append(f"{path.relative_to(_ANSIBLE)}:{lineno}: {line.strip()}")
    assert not offenders, "chromadb_service_owner derived from the caller's role list, not host state: " + "; ".join(
        offenders
    )


def test_the_two_group_vars_copies_and_deploy_yml_agree_on_the_derivation():
    """Both `role_active_facts.yml` copies already derive
    `chromadb_service_owner` from `role_redis_active` (guarded byte-for-byte
    by `ansible/tests/check_role_facts_synced.py`). deploy.yml's `vars_files`
    entry must point at the SAME file, or the two "stacks" resolve the same
    variable name to two different formulas depending on which one happened
    to link group_vars."""
    canonical = _ANSIBLE / "playbooks" / "vars" / "role_active_facts.yml"
    text = canonical.read_text(encoding="utf-8")
    owner_line = next(ln for ln in text.splitlines() if ln.startswith("chromadb_service_owner:"))
    assert "role_redis_active" in owner_line, f"{canonical} no longer derives ownership from host state"

    play = _deploy_play()
    vars_files = [Path(v) for v in play.get("vars_files") or []]
    resolved = {(_ANSIBLE / v).resolve() for v in vars_files}
    assert (
        canonical.resolve() in resolved
    ), "deploy.yml's vars_files does not point at the canonical role_active_facts.yml"
