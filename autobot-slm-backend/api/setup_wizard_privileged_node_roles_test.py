# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A detected-but-undeclared privileged role must not activate through the
SETUP-WIZARD inventory path specifically (#14594).

``services/inventory_privileged_node_roles_test.py`` (#14589) proved the
dynamic-inventory path (``inventory_builder.build_registry_inventory``) is
safe. It did not exercise ``api/setup_wizard.py`` at all -- that producer
built ``node_roles`` from the ``NodeRole`` assignment table and, until this
change, never stamped ``node_roles_declared``, so the fallback
(``node_roles_declared | default(node_roles | default([]))``) silently kept
gating every setup-wizard-generated inventory on the raw union. It was safe
only because every current NodeRole writer happens to keep the table
declared-only (see ``api/nodes.py._declare_role_on_node``, #14552) -- nothing
asserted that, and nothing here proved the setup-wizard path itself was safe.

This module drives ``api.setup_wizard``'s own hostvar-building functions
(``_apply_role_host_vars``, ``_inject_co_located_ai_stack``) end to end and
renders the real ``role_active_facts.yml`` against the resulting hostvars,
exactly as ``inventory_privileged_node_roles_test.py`` does for the dynamic
path. The two should now behave identically for a detected-only node.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

yaml = pytest.importorskip("yaml")
jinja2 = pytest.importorskip("jinja2")

from api.setup_wizard import _apply_role_host_vars, _inject_co_located_ai_stack, _sanitize_ansible_name  # noqa: E402

_SLM_ROOT = Path(__file__).resolve().parent.parent
_FACTS_FILE = _SLM_ROOT / "ansible" / "playbooks" / "vars" / "role_active_facts.yml"

_PRIVILEGED_FACTS = frozenset(
    {
        "role_backend_active",
        "role_frontend_active",
        "role_ai_stack_active",
        "role_npu_worker_active",
        "role_browser_active",
    }
)


def _load_facts() -> dict[str, str]:
    data = yaml.safe_load(_FACTS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if k.startswith("role_") and k.endswith("_active")}


def _render_all(facts: dict[str, str], context: dict) -> dict[str, bool]:
    env = jinja2.Environment()
    rendered: dict[str, bool] = {}
    for name, expr in facts.items():
        rendered[name] = env.from_string(expr).render(context).strip() == "True"
    return rendered


def _wizard_hostvars(node_id: str, roles: list[str], node_role_names: list[str]) -> dict:
    """Build one host's vars the way _generate_dynamic_inventory does.

    ``roles`` is the node's declared ``Node.roles``. ``node_role_names`` is
    every ``NodeRole`` row's ``role_name`` for the node -- deliberately
    allowed to diverge from ``roles`` here, to prove node_roles_declared
    does not follow that table.
    """
    host_key = _sanitize_ansible_name(node_id)
    hosts = {host_key: {"ansible_host": "127.0.0.1"}}
    node = SimpleNamespace(node_id=node_id, ansible_target=node_id, extra_data={}, roles=roles)
    all_node_roles = [SimpleNamespace(node_id=node_id, role_name=r) for r in node_role_names]
    _apply_role_host_vars(hosts, [node], all_node_roles)
    return hosts[host_key]


def test_detected_only_node_does_not_activate_privileged_facts_via_wizard():
    """The #14560 reproduction, driven through api.setup_wizard specifically.

    A NodeRole row exists for every privileged role (simulating a producer
    that stamped the assignment table without the node ever declaring the
    role), but Node.roles is empty -- nothing was declared.
    """
    facts = _load_facts()
    detected = ["frontend", "backend", "ai-stack", "npu-worker", "browser-service", "tts-worker"]
    hostvars = _wizard_hostvars("detected-only-node", roles=[], node_role_names=detected)

    assert hostvars["node_roles"] == detected, "node_roles stays the NodeRole-table content, unfiltered"
    assert hostvars["node_roles_declared"] == [], "nothing was declared, so node_roles_declared must be empty"

    context = {**hostvars, "groups": {}, "inventory_hostname": "detected-only-node"}
    result = _render_all(facts, context)

    still_active = {name for name in _PRIVILEGED_FACTS if result[name]}
    assert (
        not still_active
    ), f"privileged fact(s) activated for a wizard-built detected-only node: {sorted(still_active)}"
    assert result["role_tts_worker_active"] is True, "deliberately-union fact must still activate off node_roles"


def test_declared_node_still_activates_via_wizard():
    facts = _load_facts()
    hostvars = _wizard_hostvars("declared-frontend-node", roles=["frontend"], node_role_names=["frontend"])

    context = {**hostvars, "groups": {}, "inventory_hostname": "declared-frontend-node"}
    result = _render_all(facts, context)

    assert result["role_frontend_active"] is True
    assert result["role_backend_active"] is False


def test_co_located_ai_stack_injection_activates_role_ai_stack_active_via_wizard():
    """Non-regression for #3461 through the #14594 fix: the co-location
    injection is a deliberate system decision and must keep activating
    role_ai_stack_active even though node_roles_declared now gates it.
    """
    facts = _load_facts()
    host_key = _sanitize_ansible_name("01-Backend")
    hosts = {host_key: {"ansible_host": "127.0.0.1"}}
    node = SimpleNamespace(node_id="01-Backend", ansible_target="01-Backend", extra_data={}, roles=["backend"])
    all_node_roles = [SimpleNamespace(node_id="01-Backend", role_name="backend")]
    _apply_role_host_vars(hosts, [node], all_node_roles)
    _inject_co_located_ai_stack(hosts, [node], fleet_has_ai_stack=False)

    context = {**hosts[host_key], "groups": {}, "inventory_hostname": host_key}
    result = _render_all(facts, context)

    assert result["role_ai_stack_active"] is True, "co-located ai-stack injection (#3461) must survive #14594's gate"
