# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for services.inventory_builder (Issue #10110).

Isolated: imports only inventory_builder + stdlib dataclasses.
No SQLAlchemy, no DB, no subprocess — safe to run with bare pytest.
"""

from dataclasses import dataclass, field
from typing import Optional

import pytest

from services.inventory_builder import (
    REQUIRED_GROUPS,
    build_registry_inventory,
    validate_inventory,
    _role_tokens_to_groups,
)


# ---------------------------------------------------------------------------
# Node stub — duck-types the Node ORM; no SQLAlchemy required in tests
# ---------------------------------------------------------------------------

@dataclass
class _Node:
    node_id: str
    ip_address: str
    roles: list = field(default_factory=list)
    detected_roles: list = field(default_factory=list)
    ssh_user: Optional[str] = None
    ssh_port: Optional[int] = None
    ansible_name: Optional[str] = None
    hostname: str = "host"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _local(ip: str) -> bool:
    """Stub: only loopback is local."""
    return ip in {"127.0.0.1", "::1", "localhost"}


def _build(nodes, local_ip_check=_local):
    return build_registry_inventory(nodes, local_ip_check)


# ---------------------------------------------------------------------------
# host name == node_id  (#10109)
# ---------------------------------------------------------------------------

def test_host_name_equals_node_id():
    """Host name in inventory MUST equal node.node_id so --limit <node_id> works."""
    node = _Node(node_id="01-Backend", ip_address="10.0.0.2", roles=["backend"])
    inv = _build([node])
    hosts = inv["all"]["hosts"]
    assert "01-Backend" in hosts, "host name must be node_id"
    assert hosts["01-Backend"]["slm_node_id"] == "01-Backend"


def test_host_name_is_node_id_not_ansible_name():
    """ansible_name field must NOT become the inventory host name."""
    node = _Node(node_id="mynode-42", ip_address="10.0.0.5", roles=["backend"],
                 ansible_name="some-alias")
    inv = _build([node])
    hosts = inv["all"]["hosts"]
    assert "mynode-42" in hosts
    assert "some-alias" not in hosts


# ---------------------------------------------------------------------------
# self-node (local IP) → ansible_connection: local  (#10095)
# ---------------------------------------------------------------------------

def test_local_ip_gets_local_connection():
    """Self-node (loopback IP) must receive ansible_connection: local."""
    node = _Node(node_id="00-SLM-Manager", ip_address="127.0.0.1", roles=["slm-backend"])
    inv = _build([node], local_ip_check=_local)
    hostvars = inv["all"]["hosts"]["00-SLM-Manager"]
    assert hostvars.get("ansible_connection") == "local"


def test_remote_ip_no_local_connection():
    """Remote node must NOT have ansible_connection: local."""
    node = _Node(node_id="01-Backend", ip_address="192.168.1.10", roles=["backend"])
    inv = _build([node], local_ip_check=_local)
    hostvars = inv["all"]["hosts"]["01-Backend"]
    assert "ansible_connection" not in hostvars


def test_custom_local_check_injectable():
    """local_ip_check is injectable; any IP the caller declares local is treated as local."""
    node = _Node(node_id="01-Backend", ip_address="10.0.0.1", roles=["backend"])
    inv = _build([node], local_ip_check=lambda ip: ip == "10.0.0.1")
    assert inv["all"]["hosts"]["01-Backend"].get("ansible_connection") == "local"


# ---------------------------------------------------------------------------
# hostvars completeness
# ---------------------------------------------------------------------------

def test_hostvars_defaults():
    """ssh_user and ssh_port default to 'autobot' and 22 when None."""
    node = _Node(node_id="02-Frontend", ip_address="10.0.0.3", roles=["frontend"],
                 ssh_user=None, ssh_port=None)
    inv = _build([node])
    h = inv["all"]["hosts"]["02-Frontend"]
    assert h["ansible_user"] == "autobot"
    assert h["ansible_port"] == 22
    assert h["ansible_host"] == "10.0.0.3"


def test_hostvars_explicit_values():
    """Node-specific ssh_user and ssh_port are used when set."""
    node = _Node(node_id="05-LLM-CPU", ip_address="10.0.0.9", roles=["autobot-llm-cpu"],
                 ssh_user="ubuntu", ssh_port=2222)
    inv = _build([node])
    h = inv["all"]["hosts"]["05-LLM-CPU"]
    assert h["ansible_user"] == "ubuntu"
    assert h["ansible_port"] == 2222


# ---------------------------------------------------------------------------
# role → group mapping
# ---------------------------------------------------------------------------

def test_slm_node_groups():
    """slm-backend role → slm, slm_server, slm_nodes; NOT in infrastructure."""
    node = _Node(node_id="00-SLM-Manager", ip_address="127.0.0.1", roles=["slm-backend"])
    inv = _build([node])
    children = inv["all"]["children"]
    host = "00-SLM-Manager"
    assert host in children["slm"]["hosts"]
    assert host in children["slm_server"]["hosts"]
    assert host in children["slm_nodes"]["hosts"]
    # SLM node does NOT join infrastructure
    assert host not in children.get("infrastructure", {}).get("hosts", {})


def test_backend_node_groups():
    """backend role → backend, main, infrastructure, autobot, autobot_cluster."""
    node = _Node(node_id="01-Backend", ip_address="10.0.0.2", roles=["backend"])
    inv = _build([node])
    children = inv["all"]["children"]
    host = "01-Backend"
    assert host in children["backend"]["hosts"]
    assert host in children["main"]["hosts"]
    assert host in children["infrastructure"]["hosts"]
    assert host in children["autobot"]["hosts"]
    assert host in children["autobot_cluster"]["hosts"]


def test_npu_node_groups():
    """npu-worker role → npu, npu_worker, npu_workers."""
    node = _Node(node_id="npu-worker", ip_address="10.0.0.6", roles=["npu-worker"])
    inv = _build([node])
    children = inv["all"]["children"]
    host = "npu-worker"
    assert host in children["npu"]["hosts"]
    assert host in children["npu_worker"]["hosts"]
    assert host in children["npu_workers"]["hosts"]


def test_ai_stack_node_groups():
    """ai-stack role → ai_stack, aiml, ai, llm_nodes."""
    node = _Node(node_id="03-AI-Stack", ip_address="10.0.0.7", roles=["ai-stack"])
    inv = _build([node])
    children = inv["all"]["children"]
    host = "03-AI-Stack"
    assert host in children["ai_stack"]["hosts"]
    assert host in children["aiml"]["hosts"]
    assert host in children["ai"]["hosts"]
    assert host in children["llm_nodes"]["hosts"]


def test_llm_cpu_prefix_role_groups():
    """autobot-llm-cpu prefix role → ai_stack, aiml, ai, llm_nodes."""
    node = _Node(node_id="05-LLM-CPU", ip_address="10.0.0.8", roles=["autobot-llm-cpu"])
    inv = _build([node])
    children = inv["all"]["children"]
    host = "05-LLM-CPU"
    assert host in children["ai_stack"]["hosts"]
    assert host in children["llm_nodes"]["hosts"]


def test_database_node_groups():
    """redis role → database and redis groups."""
    node = _Node(node_id="04-Databases", ip_address="10.0.0.5", roles=["redis"])
    inv = _build([node])
    children = inv["all"]["children"]
    host = "04-Databases"
    assert host in children["database"]["hosts"]
    assert host in children["redis"]["hosts"]


def test_browser_node_groups():
    """browser-service role → browser and browser_worker groups."""
    node = _Node(node_id="browser-automation", ip_address="10.0.0.11", roles=["browser-service"])
    inv = _build([node])
    children = inv["all"]["children"]
    host = "browser-automation"
    assert host in children["browser"]["hosts"]
    assert host in children["browser_worker"]["hosts"]


def test_monitoring_node_groups():
    """monitoring role → monitoring_vm group."""
    node = _Node(node_id="mon-01", ip_address="10.0.0.20", roles=["monitoring"])
    inv = _build([node])
    children = inv["all"]["children"]
    assert "mon-01" in children["monitoring_vm"]["hosts"]


def test_frontend_node_in_infrastructure():
    """frontend role → frontend group AND infrastructure (not SLM)."""
    node = _Node(node_id="02-Frontend", ip_address="10.0.0.3", roles=["frontend"])
    inv = _build([node])
    children = inv["all"]["children"]
    assert "02-Frontend" in children["frontend"]["hosts"]
    assert "02-Frontend" in children["infrastructure"]["hosts"]


def test_detected_roles_merged_with_roles():
    """detected_roles are unioned with roles for group mapping."""
    node = _Node(
        node_id="01-Backend",
        ip_address="10.0.0.2",
        roles=["backend"],
        detected_roles=["redis"],
    )
    inv = _build([node])
    children = inv["all"]["children"]
    host = "01-Backend"
    assert host in children["backend"]["hosts"]
    assert host in children["redis"]["hosts"]
    assert host in children["database"]["hosts"]


def test_production_vms_alias_present():
    """Non-SLM nodes join production_vms (alias for infrastructure, deploy-time-sync.yml)."""
    node = _Node(node_id="01-Backend", ip_address="10.0.0.2", roles=["backend"])
    inv = _build([node])
    assert "01-Backend" in inv["all"]["children"]["production_vms"]["hosts"]


# ---------------------------------------------------------------------------
# global all.vars reproduced
# ---------------------------------------------------------------------------

def test_all_vars_present():
    """Generated inventory must include every global var from slm-nodes.yml."""
    inv = _build([])
    vars_ = inv["all"]["vars"]
    assert vars_["ansible_user"] == "autobot"
    assert vars_["ansible_ssh_private_key_file"] == "/etc/autobot/ssh/autobot_key"
    assert vars_["ansible_python_interpreter"] == "/usr/bin/python3"
    assert "slm_host" in vars_
    assert "network_subnet" in vars_
    assert "network_gateway" in vars_


# ---------------------------------------------------------------------------
# validate_inventory
# ---------------------------------------------------------------------------

def test_validate_passes_when_all_required_groups_present():
    """validate_inventory does not raise when all required groups are present."""
    slm = _Node(node_id="00-SLM-Manager", ip_address="127.0.0.1", roles=["slm-backend"])
    be = _Node(node_id="01-Backend", ip_address="10.0.0.2", roles=["backend"])
    fe = _Node(node_id="02-Frontend", ip_address="10.0.0.3", roles=["frontend"])
    npu = _Node(node_id="npu-worker", ip_address="10.0.0.6", roles=["npu-worker"])
    ai = _Node(node_id="03-AI-Stack", ip_address="10.0.0.7", roles=["ai-stack"])
    db = _Node(node_id="04-Databases", ip_address="10.0.0.5", roles=["redis"])
    br = _Node(node_id="browser-auto", ip_address="10.0.0.11", roles=["browser-service"])
    mon = _Node(node_id="mon-01", ip_address="10.0.0.20", roles=["monitoring"])
    inv = _build([slm, be, fe, npu, ai, db, br, mon])
    validate_inventory(inv)  # must not raise


def test_validate_raises_on_missing_group():
    """validate_inventory raises ValueError naming every missing group."""
    node = _Node(node_id="00-SLM-Manager", ip_address="127.0.0.1", roles=["slm-backend"])
    inv = _build([node])
    del inv["all"]["children"]["frontend"]
    with pytest.raises(ValueError, match="frontend"):
        validate_inventory(inv)


def test_validate_empty_group_is_ok():
    """A group key with no hosts is allowed (present but empty)."""
    node = _Node(node_id="00-SLM-Manager", ip_address="127.0.0.1", roles=["slm-backend"])
    inv = _build([node])
    assert "frontend" in inv["all"]["children"]
    assert inv["all"]["children"]["frontend"]["hosts"] == {}
    validate_inventory(inv)  # must not raise


def test_validate_custom_required_set():
    """validate_inventory accepts a caller-supplied required_groups frozenset."""
    inv = _build([])
    # Only require 'autobot' — passes even with no nodes
    validate_inventory(inv, required_groups=frozenset({"autobot"}))
    # Require a nonexistent group to prove it raises
    with pytest.raises(ValueError, match="nonexistent_group"):
        validate_inventory(inv, required_groups=frozenset({"nonexistent_group"}))


# ---------------------------------------------------------------------------
# 2-node fixture: SLM self-node + remote backend (sample inventory dump)
# ---------------------------------------------------------------------------

def test_two_node_fixture_structure():
    """2-node fixture: SLM self-node gets local conn; backend gets SSH; all groups valid."""
    slm_node = _Node(
        node_id="00-SLM-Manager",
        ip_address="127.0.0.1",
        roles=["slm-backend", "slm-agent"],
    )
    backend_node = _Node(
        node_id="01-Backend",
        ip_address="192.168.1.10",
        roles=["backend", "celery", "scheduler"],
        ssh_user="autobot",
        ssh_port=22,
    )
    inv = _build([slm_node, backend_node], local_ip_check=_local)

    # SLM: local connection (#10095)
    assert inv["all"]["hosts"]["00-SLM-Manager"]["ansible_connection"] == "local"
    # Backend: no local connection
    assert "ansible_connection" not in inv["all"]["hosts"]["01-Backend"]

    # All required groups present
    validate_inventory(inv)

    children = inv["all"]["children"]
    # SLM in slm groups, NOT in infrastructure
    slm_h = "00-SLM-Manager"
    assert slm_h in children["slm"]["hosts"]
    assert slm_h in children["slm_server"]["hosts"]
    assert slm_h not in children["infrastructure"]["hosts"]

    # Backend in backend/main/infrastructure/autobot (#10109 — --limit 01-Backend works)
    be_h = "01-Backend"
    assert be_h in children["backend"]["hosts"]
    assert be_h in children["main"]["hosts"]
    assert be_h in children["infrastructure"]["hosts"]
    assert be_h in children["autobot"]["hosts"]


# ---------------------------------------------------------------------------
# _role_tokens_to_groups unit tests
# ---------------------------------------------------------------------------

def test_role_tokens_prefix_match():
    """'slm-backend' matches 'slm-' prefix key."""
    g = _role_tokens_to_groups(["slm-backend"])
    assert "slm" in g
    assert "slm_server" in g
    assert "slm_nodes" in g


def test_role_tokens_exact_match():
    """'redis' matches 'redis' exact key."""
    g = _role_tokens_to_groups(["redis"])
    assert "redis" in g
    assert "database" in g


def test_role_tokens_unknown_produces_empty():
    """Unknown role tokens produce no groups."""
    g = _role_tokens_to_groups(["docker", "unknown-service"])
    assert len(g) == 0


def test_role_tokens_multiple_accumulate():
    """Multiple tokens accumulate their groups."""
    g = _role_tokens_to_groups(["backend", "redis"])
    assert "backend" in g
    assert "main" in g
    assert "redis" in g
    assert "database" in g


def test_role_tokens_autobot_llm_prefix():
    """'autobot-llm-gpu' matches 'autobot-llm-' prefix key."""
    g = _role_tokens_to_groups(["autobot-llm-gpu"])
    assert "ai_stack" in g
    assert "llm_nodes" in g


# ---------------------------------------------------------------------------
# REQUIRED_GROUPS covers known playbook group references
# ---------------------------------------------------------------------------

def test_required_groups_covers_known_playbook_references():
    """Spot-check known groups from playbook grep against REQUIRED_GROUPS."""
    known = {
        "slm_server", "slm", "slm_nodes",
        "backend", "main", "frontend",
        "npu", "npu_workers",
        "ai_stack", "aiml", "ai",
        "database", "redis",
        "browser", "browser_worker",
        "infrastructure",
        "autobot", "autobot_cluster",
        "monitoring_vm",
        "llm_nodes",
        "production_vms",
    }
    missing = known - REQUIRED_GROUPS
    assert not missing, f"REQUIRED_GROUPS is missing known group refs: {missing}"
