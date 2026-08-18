# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every group whose play deploys a component must be declaration-gated (#14552).

#14513 stopped detection granting `slm_server`, `backend` and `main`, because
those plays unpack a tree and run migrations. It missed `frontend`, and the gap
showed up in production as::

    TASK [[PLAY 2] Frontend | Rebuild production dist]
    fatal: cmd "npx vite build" -> [Errno 2] No such file or directory: b'npx'

on a `[vnc, slm-agent]` node with no Node.js. Play 2 gates its deploy tasks on
exactly two groups, `backend` and `frontend`; gating one of them left the other
half of the same play wide open.

The lesson is not "add frontend" -- it is that a hand-picked list drifts from
the playbook it is supposed to mirror. So the expected set is DERIVED here from
`update-all-nodes.yml`, and this fails if a component is ever added to that play
without being added to `_DECLARED_ONLY_GROUPS`.

The constant stays in code: production must not parse a playbook to build an
inventory. Only the assertion is derived.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_SLM_ROOT = Path(__file__).resolve().parent.parent
_PLAYBOOK = _SLM_ROOT / "ansible" / "playbooks" / "update-all-nodes.yml"


def _load_inventory_builder():
    name = "_inventory_builder_deploy_groups"
    spec = importlib.util.spec_from_file_location(name, _SLM_ROOT / "services" / "inventory_builder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


inventory_builder = _load_inventory_builder()


def _groups_gating_deploy_tasks() -> set[str]:
    """Groups the update playbook gates component deploys on.

    Read as text rather than parsed: the gates are Jinja expressions inside
    `when:`, and what matters is which group name each one tests.
    """
    text = _PLAYBOOK.read_text(encoding="utf-8")
    return set(re.findall(r"when:\s*\"'([a-z_]+)' in group_names\"", text))


def _plays_targeting_a_group_directly() -> set[str]:
    """Groups a whole play targets via `hosts:` — Play 1 uses this for slm_server."""
    documents = list(yaml.safe_load_all(_PLAYBOOK.read_text(encoding="utf-8")))
    hosts = set()
    for document in documents:
        for play in document if isinstance(document, list) else [document]:
            if isinstance(play, dict) and isinstance(play.get("hosts"), str):
                hosts.add(play["hosts"])
    return hosts


def test_the_derivation_finds_the_playbook_and_its_gates():
    """A derivation that finds nothing would make the rule below vacuous."""
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} is gone — this rule is pinned to the wrong path"

    gates = _groups_gating_deploy_tasks()

    assert gates, "no `'x' in group_names` gates parsed — the playbook's shape changed"
    assert "backend" in gates and "frontend" in gates, (
        f"expected the two known deploy gates in Play 2, found {sorted(gates)}"
    )


def test_every_deploy_gated_group_is_declaration_gated():
    """The #14552 invariant.

    If the update playbook will deploy a component to whoever is in group X,
    then landing in X must require the operator to have declared it.
    """
    missing = sorted(_groups_gating_deploy_tasks() - set(inventory_builder._DECLARED_ONLY_GROUPS))

    assert not missing, (
        f"group(s) receive a component deploy but detection can still grant them: {missing}. "
        "A node that never declared the role gets the tree unpacked and its build/restart tasks run "
        "(#14552 — this is how `frontend` was missed after #14513)"
    )


def test_play_one_target_is_declaration_gated():
    """Play 1 targets `slm_server` by `hosts:`, not by a group_names gate."""
    slm_plays = _plays_targeting_a_group_directly() & {"slm_server"}

    assert slm_plays, "no play targets slm_server directly — Play 1's shape changed"
    assert "slm_server" in inventory_builder._DECLARED_ONLY_GROUPS


def test_ordinary_groups_are_not_swept_in():
    """The gate must stay narrow enough that detection still adds ordinary groups.

    `redis`/`database` are granted by detection on purpose — a node genuinely
    running redis should keep receiving redis updates, which
    `test_detected_roles_merged_with_roles` pins independently.
    """
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)

    assert "redis" not in gated and "database" not in gated, (
        "redis/database became declaration-gated — that is a larger behaviour change than #14552"
    )
