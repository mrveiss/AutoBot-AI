# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit test: wizard inventory stamps node_roles via the sanitized host key (#9965).

_apply_role_host_vars must look up hosts by the SAME sanitized ansible name that
_fetch_inventory_data uses as the host key. Previously it used the raw
node.ansible_target (e.g. '00-SLM-Manager') which never matched the sanitized
key ('node_00_SLM_Manager'), so node_roles was never stamped and optional roles
(tts-worker, browser-service) silently never deployed.

Also covers #14594: node_roles_declared must be stamped from node.roles alone,
never from the NodeRole rows node_roles itself is built from.
"""

from types import SimpleNamespace

from api.setup_wizard import _apply_role_host_vars, _sanitize_ansible_name


def test_apply_role_host_vars_stamps_via_sanitized_key():
    raw = "00-SLM-Manager"
    host_key = _sanitize_ansible_name(raw)
    assert host_key != raw, "node id should require sanitizing for this test to be meaningful"

    hosts = {host_key: {"ansible_host": "127.0.0.1"}}
    node = SimpleNamespace(node_id="00-SLM-Manager", ansible_target=raw, extra_data={}, roles=["ai-stack"])
    all_node_roles = [
        SimpleNamespace(node_id="00-SLM-Manager", role_name="tts-worker"),
        SimpleNamespace(node_id="00-SLM-Manager", role_name="browser-service"),
        SimpleNamespace(node_id="00-SLM-Manager", role_name="ai-stack"),
    ]

    _apply_role_host_vars(hosts, [node], all_node_roles)

    assert "node_roles" in hosts[host_key]
    for role in ("tts-worker", "browser-service", "ai-stack"):
        assert role in hosts[host_key]["node_roles"]


def test_apply_role_host_vars_declared_excludes_undeclared_node_role_rows():
    """#14594: a NodeRole row does not, by itself, make a role "declared".

    node_roles_declared must come from node.roles alone -- if a NodeRole row
    ever exists for a role the node's own `roles` list does not carry (today
    every writer keeps them in sync, see api/nodes.py._declare_role_on_node,
    but that is a fact about the writers, not a guarantee this hostvar should
    depend on), node_roles_declared must not pick it up.
    """
    raw = "00-SLM-Manager"
    host_key = _sanitize_ansible_name(raw)
    hosts = {host_key: {"ansible_host": "127.0.0.1"}}
    # Declares only "backend"; a "frontend" NodeRole row exists regardless
    # (simulating a future writer that stamps NodeRole without node.roles).
    node = SimpleNamespace(node_id="00-SLM-Manager", ansible_target=raw, extra_data={}, roles=["backend"])
    all_node_roles = [
        SimpleNamespace(node_id="00-SLM-Manager", role_name="backend"),
        SimpleNamespace(node_id="00-SLM-Manager", role_name="frontend"),
    ]

    _apply_role_host_vars(hosts, [node], all_node_roles)

    assert "frontend" in hosts[host_key]["node_roles"], "node_roles stays the NodeRole-table union"
    assert hosts[host_key]["node_roles_declared"] == ["backend"]
    assert "frontend" not in hosts[host_key]["node_roles_declared"]


def test_apply_role_host_vars_declared_defaults_empty_when_no_roles():
    raw = "00-SLM-Manager"
    host_key = _sanitize_ansible_name(raw)
    hosts = {host_key: {"ansible_host": "127.0.0.1"}}
    node = SimpleNamespace(node_id="00-SLM-Manager", ansible_target=raw, extra_data={}, roles=[])

    _apply_role_host_vars(hosts, [node], [])

    assert hosts[host_key]["node_roles_declared"] == []
