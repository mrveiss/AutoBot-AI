# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit test: co-located ai-stack injection stamps node_roles_declared too (#14594).

_inject_co_located_ai_stack (#3461) silently adds "ai-stack" to a co-located
backend node's node_roles so Phase 5a deploys ChromaDB, even though the
operator never declared ai-stack anywhere. role_ai_stack_active is one of the
five PRIVILEGED facts #14560/#14589 repointed at node_roles_declared instead
of the raw union -- so the injection must land in node_roles_declared too, or
this deliberate co-location convenience silently stops deploying ChromaDB the
moment node_roles_declared exists (a regression this test guards against).
"""

from types import SimpleNamespace

from api.setup_wizard import _apply_role_host_vars, _inject_co_located_ai_stack, _sanitize_ansible_name


def _build_hosts(role_name: str):
    raw = "01-Backend"
    host_key = _sanitize_ansible_name(raw)
    hosts = {host_key: {"ansible_host": "127.0.0.1"}}
    node = SimpleNamespace(node_id="01-Backend", ansible_target=raw, extra_data={}, roles=[role_name])
    all_node_roles = [SimpleNamespace(node_id="01-Backend", role_name=role_name)]
    _apply_role_host_vars(hosts, [node], all_node_roles)
    return hosts, [node], host_key


def test_injection_adds_ai_stack_to_both_hostvars_when_fleet_lacks_it():
    hosts, db_nodes, host_key = _build_hosts("backend")

    injected = _inject_co_located_ai_stack(hosts, db_nodes, fleet_has_ai_stack=False)

    assert injected == [host_key]
    assert "ai-stack" in hosts[host_key]["node_roles"]
    assert "ai-stack" in hosts[host_key]["node_roles_declared"], (
        "ai-stack co-location injection (#3461) must also land in node_roles_declared "
        "or role_ai_stack_active silently stops firing for it (#14594)"
    )


def test_injection_is_noop_when_fleet_already_has_ai_stack():
    hosts, db_nodes, host_key = _build_hosts("backend")

    injected = _inject_co_located_ai_stack(hosts, db_nodes, fleet_has_ai_stack=True)

    assert injected == []
    assert "ai-stack" not in hosts[host_key]["node_roles"]
    assert "ai-stack" not in hosts[host_key]["node_roles_declared"]


def test_injection_skips_non_backend_nodes():
    hosts, db_nodes, host_key = _build_hosts("frontend")

    injected = _inject_co_located_ai_stack(hosts, db_nodes, fleet_has_ai_stack=False)

    assert injected == []
    assert "ai-stack" not in hosts[host_key].get("node_roles_declared", [])
