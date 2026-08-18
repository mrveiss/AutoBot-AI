# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A detected-but-undeclared privileged role must not activate its deploy (#14560).

#14513/#14552 gated the ansible GROUP branch of role_active_facts.yml's
OR-chains: a node that only *detected* ``frontend`` no longer joins the
``frontend`` ansible group. ``provision-fleet-roles.yml`` does not read the
group alone -- every gate is ``when: role_X_active``, and that fact also has
a ``node_roles`` branch. ``node_roles`` is the UNION of declared and detected
roles (``inventory_builder._union_roles``), and the union was never filtered,
so a detected-only node still evaluated the privileged facts (backend,
frontend, ai_stack, npu_worker, browser) true and got the tree unpacked --
the same failure #14552 fixed, reached through provisioning instead of the
update playbook.

The fix stamps a second hostvar, ``node_roles_declared`` (declared roles
only, see ``inventory_builder._declared_roles``), and repoints the five
privileged facts' node_roles branch at it. The other facts (redis, vnc,
xrdp, llm, tts_worker) deliberately keep the raw ``node_roles`` union --
``role_tts_worker_active`` in particular has no group fallback at all
(#9965), so node_roles is its only activation path by design.

This module does not hand-list which facts are "privileged": it DERIVES the
set from ``inventory_builder._DECLARED_ONLY_GROUPS`` (the group set #14552
already proved matches the playbook, via ``inventory_deploy_groups_test.py``)
by checking which facts' ``groups.get(...)`` branches reference one of those
groups. A fact gains "privileged" status automatically the moment it starts
gating on a privileged group, so this fails loud on a sixth fact without
anyone maintaining a parallel list.

Extraction uses ``yaml.safe_load`` rather than a scalar-style-specific regex
-- #14555's derivation regex anchored on one YAML quoting form and silently
missed 33 of 60 occurrences written in a different style. ``yaml.safe_load``
resolves the fact value to a plain string regardless of whether it is a
folded (``>-``), literal (``|``), plain, or quoted scalar.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
jinja2 = pytest.importorskip("jinja2")

_SLM_ROOT = Path(__file__).resolve().parent.parent
_FACTS_FILE = _SLM_ROOT / "ansible" / "playbooks" / "vars" / "role_active_facts.yml"
_PROVISION_PLAYBOOK = _SLM_ROOT / "ansible" / "playbooks" / "provision-fleet-roles.yml"

# Facts the #9965 comment on inventory_builder._build_hostvars names as
# activating via node_roles BY DESIGN, with no (or an incomplete) group
# fallback. Used only as a non-regression pin (test below), never as the
# source of the privileged/non-privileged split itself -- that split is
# derived, see _privileged_facts().
_DELIBERATELY_UNION_FACTS = frozenset(
    {
        "role_tts_worker_active",
        "role_redis_active",
        "role_vnc_active",
        "role_xrdp_active",
        "role_llm_active",
    }
)

_GROUPS_GET_RE = re.compile(r"""groups\.get\(\s*['"]([a-zA-Z0-9_]+)['"]""")
# "'x' in (node_roles ...)" but NOT "'x' in (node_roles_declared ...)" -- the
# underscore after node_roles makes \b fail to match at that boundary, so
# this pattern already skips the declared variant and the `default(...)`
# fallback (which is never preceded by `in (`).
_RAW_NODE_ROLES_MEMBERSHIP_RE = re.compile(r"in\s*\(\s*node_roles(?!_declared)\b")


def _load_inventory_builder():
    name = "_inventory_builder_privileged_node_roles"
    spec = importlib.util.spec_from_file_location(name, _SLM_ROOT / "services" / "inventory_builder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


inventory_builder = _load_inventory_builder()


def _load_facts() -> dict[str, str]:
    """fact name -> its Jinja expression string, however it was quoted in YAML."""
    data = yaml.safe_load(_FACTS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if k.startswith("role_") and k.endswith("_active")}


def _facts_consumed_by_provision_playbook() -> set[str]:
    text = _PROVISION_PLAYBOOK.read_text(encoding="utf-8")
    return set(re.findall(r"\brole_\w+_active\b", text))


def _privileged_facts(facts: dict[str, str]) -> set[str]:
    """Facts gated on a privileged group AND carrying a node_roles branch.

    Both conditions matter: ``role_slm_active`` also gates on a privileged
    group (``slm_server``), but it has no node_roles branch at all -- it is
    pure group membership, already correctly gated by
    ``_strip_undeclared_privileged_groups`` on the group side, with nothing
    for this fix to touch. Requiring a node_roles branch too is what narrows
    the derived set to exactly the five #14560 names (backend, frontend,
    ai_stack, npu_worker, browser) without hand-listing them.
    """
    privileged = set()
    for name, expr in facts.items():
        referenced_groups = set(_GROUPS_GET_RE.findall(expr))
        gates_privileged_group = bool(referenced_groups & set(inventory_builder._DECLARED_ONLY_GROUPS))
        has_node_roles_branch = "node_roles" in expr
        if gates_privileged_group and has_node_roles_branch:
            privileged.add(name)
    return privileged


def _render_all(facts: dict[str, str], context: dict) -> dict[str, bool]:
    env = jinja2.Environment()
    rendered: dict[str, bool] = {}
    for name, expr in facts.items():
        rendered[name] = env.from_string(expr).render(context).strip() == "True"
    return rendered


def test_measured_reach():
    """The numbers #14560 asks to be measured, not assumed."""
    facts = _load_facts()
    consumed = _facts_consumed_by_provision_playbook() & set(facts)
    privileged = _privileged_facts(facts)

    assert facts, "role_active_facts.yml parsed to zero role_*_active facts"
    assert consumed, "no role_*_active fact referenced by provision-fleet-roles.yml"
    assert privileged, "derivation found zero privileged facts -- the rule below would be vacuous"

    # Not an assertion on the exact membership (that would be the hand list
    # this module exists to avoid) -- just that the counts are sane and
    # every privileged fact is one the playbook actually gates a deploy on.
    assert privileged <= consumed, f"privileged fact(s) not consumed by the playbook: {sorted(privileged - consumed)}"


def test_privileged_facts_use_declared_only_node_roles():
    """The #14560 invariant: no privileged fact tests the raw union anymore."""
    facts = _load_facts()
    privileged = _privileged_facts(facts)

    leaking = {name for name in privileged if _RAW_NODE_ROLES_MEMBERSHIP_RE.search(facts[name])}
    assert not leaking, (
        f"{sorted(leaking)} gate a privileged group but still test the raw (union) node_roles -- "
        "a detected-but-undeclared node still activates them (#14560)"
    )


def test_deliberately_union_facts_are_not_swept_in():
    """Non-regression: #9965's deliberately-union facts keep their only path."""
    facts = _load_facts()
    privileged = _privileged_facts(facts)

    missing = _DELIBERATELY_UNION_FACTS - set(facts)
    assert not missing, f"expected deliberately-union fact(s) missing from role_active_facts.yml: {sorted(missing)}"

    reclassified = _DELIBERATELY_UNION_FACTS & privileged
    assert not reclassified, f"deliberately-union fact(s) became privileged: {sorted(reclassified)}"

    for name in _DELIBERATELY_UNION_FACTS:
        assert _RAW_NODE_ROLES_MEMBERSHIP_RE.search(
            facts[name]
        ), f"{name} lost its node_roles activation path -- role_tts_worker_active has no group fallback (#9965)"


def test_detected_only_node_does_not_activate_privileged_facts():
    """End-to-end #14560 reproduction, rendered exactly as Ansible would.

    A node whose privileged roles are DETECTED (node_roles) but never
    DECLARED (node_roles_declared empty) must not activate any of them --
    while the deliberately-union tts-worker fact still fires.
    """
    facts = _load_facts()
    privileged = _privileged_facts(facts)
    context = {
        "node_roles": ["frontend", "backend", "ai-stack", "npu-worker", "browser-service", "tts-worker"],
        "node_roles_declared": [],
        "groups": {},
        "inventory_hostname": "detected-only-node",
    }
    result = _render_all(facts, context)

    still_active = {name for name in privileged if result[name]}
    assert not still_active, f"privileged fact(s) activated for a detected-only node: {sorted(still_active)}"
    assert result["role_tts_worker_active"] is True, "deliberately-union fact must still activate off node_roles"


def test_declared_role_still_activates():
    """Over-tight check, mirrors #14552's test_ordinary_groups_are_not_swept_in.

    A role the operator genuinely declared must keep activating -- the gate
    must not become so strict that a legitimate assignment silently drops
    out of its deploy.
    """
    facts = _load_facts()
    context = {
        "node_roles": ["frontend"],
        "node_roles_declared": ["frontend"],
        "groups": {},
        "inventory_hostname": "declared-frontend-node",
    }
    result = _render_all(facts, context)

    assert result["role_frontend_active"] is True, "a declared privileged role must still activate its deploy"
    assert result["role_backend_active"] is False


def test_static_inventory_without_node_roles_declared_is_unaffected():
    """Non-regression: hosts that never stamp node_roles_declared (every
    static inventory -- localhost.yml, slm-nodes.yml, the CI test fixtures)
    must behave exactly as before -- the fallback is node_roles itself.
    """
    facts = _load_facts()
    context = {
        "node_roles": ["autobot-backend", "vnc"],
        # node_roles_declared deliberately absent, as in every static host.
        "groups": {},
        "inventory_hostname": "static-inventory-host",
    }
    result = _render_all(facts, context)

    assert result["role_backend_active"] is True
    assert result["role_vnc_active"] is True
    assert result["role_frontend_active"] is False
