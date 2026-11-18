# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nodes assigned npu-worker in the SLM are offered for pairing, and never paired here (#19706)."""

import inspect

from services import npu_worker_assignments
from services.npu_worker_assignments import unpaired_worker_nodes


def _node(ip="10.0.0.1", roles=("npu-worker",), status="online", hostname="npu-a"):
    return {"ip_address": ip, "roles": list(roles), "status": status, "hostname": hostname}


def test_an_assigned_online_node_with_no_worker_is_found():
    assert unpaired_worker_nodes([_node()], [], 8081) == {"http://10.0.0.1:8081": "npu-a"}


def test_an_already_paired_node_is_left_out():
    assert unpaired_worker_nodes([_node()], ["http://10.0.0.1:8081/"], 8081) == {}


def test_a_node_without_the_role_is_left_out():
    assert unpaired_worker_nodes([_node(roles=("redis",))], [], 8081) == {}


def test_a_node_with_no_roles_recorded_is_left_out():
    assert unpaired_worker_nodes([{"ip_address": "10.0.0.1", "roles": None, "status": "online"}], [], 8081) == {}


def test_an_offline_node_waits_until_it_is_online():
    assert unpaired_worker_nodes([_node(status="offline")], [], 8081) == {}


def test_a_node_without_a_hostname_is_named_by_its_address():
    assert unpaired_worker_nodes([_node(hostname=None)], [], 8081) == {"http://10.0.0.1:8081": "10.0.0.1"}


def test_this_module_never_pairs():
    """Pairing hands over Redis credentials, so only the admin route may do it."""
    assert "_execute_worker_pairing" not in inspect.getsource(npu_worker_assignments)
