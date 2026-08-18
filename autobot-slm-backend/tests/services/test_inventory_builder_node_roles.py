# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit test for inventory_builder node_roles stamping (Issue #9965).

Regression guard: the generated inventory must stamp each node's assigned role
tokens as the `node_roles` hostvar, so role_active_facts.yml activates roles via
node_roles (not group membership alone). Without it, optional roles whose
inventory group isn't the one role_*_active checks (tts-worker, browser-service)
never provision.
"""

from types import SimpleNamespace

from services.inventory_builder import build_registry_inventory


def _node(node_id="00-SLM-Manager", roles=None, detected=None):
    return SimpleNamespace(
        node_id=node_id,
        ip_address="127.0.0.1",
        ssh_user="autobot",
        ssh_port=22,
        roles=roles or [],
        detected_roles=detected or [],
    )


def test_node_roles_stamped_into_hostvars():
    node = _node(roles=["ai-stack", "tts-worker", "browser-service"])
    inv = build_registry_inventory([node], local_ip_check=lambda ip: True)
    hostvars = inv["all"]["hosts"]["00-SLM-Manager"]
    assert "node_roles" in hostvars, "node_roles must be stamped for role_active_facts"
    for role in ("ai-stack", "tts-worker", "browser-service"):
        assert role in hostvars["node_roles"], f"{role} missing from node_roles"


def test_node_roles_unions_detected_roles():
    node = _node(roles=["backend"], detected=["redis"])
    inv = build_registry_inventory([node], local_ip_check=lambda ip: False)
    roles = inv["all"]["hosts"]["00-SLM-Manager"]["node_roles"]
    assert "backend" in roles and "redis" in roles


def test_node_roles_declared_excludes_detected_only_roles():
    """#14560: node_roles_declared must NOT union in detected_roles.

    role_active_facts.yml's five privileged facts (backend, frontend,
    ai_stack, npu_worker, browser) read node_roles_declared instead of
    node_roles precisely so a role that was only DETECTED never activates
    their deploy tasks. If this hostvar ever unioned detected_roles back in,
    that gate would be silently defeated again.
    """
    node = _node(roles=["backend"], detected=["frontend"])
    inv = build_registry_inventory([node], local_ip_check=lambda ip: False)
    hostvars = inv["all"]["hosts"]["00-SLM-Manager"]
    assert "node_roles_declared" in hostvars, "node_roles_declared must be stamped for the privileged facts"
    assert hostvars["node_roles_declared"] == ["backend"]
    assert "frontend" not in hostvars["node_roles_declared"]
    # node_roles (the union) is unaffected -- other tests pin this stays the union.
    assert "frontend" in hostvars["node_roles"]


def test_node_roles_declared_matches_roles_only():
    node = _node(roles=["ai-stack", "tts-worker"], detected=["ai-stack", "npu-worker", "tts-worker"])
    inv = build_registry_inventory([node], local_ip_check=lambda ip: True)
    hostvars = inv["all"]["hosts"]["00-SLM-Manager"]
    assert sorted(hostvars["node_roles_declared"]) == ["ai-stack", "tts-worker"]
    assert "npu-worker" not in hostvars["node_roles_declared"]
