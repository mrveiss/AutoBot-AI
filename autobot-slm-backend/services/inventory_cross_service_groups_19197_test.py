# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A detected role grants a group only when that group's own service is present (#19197).

A vnc node that earlier mis-targeted plays left with postgresql detects
``postgres`` and ``slm-database``. ``slm-database`` maps to ``redis``/``database``,
and ``role_redis_active`` fires on either group, so the node failed on a missing
``redis-stack-server``. Declared roles keep their full mapping.
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_SLM_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, _SLM_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


ib = _load("inventory_builder_19197_under_test", "services/inventory_builder.py")

from autobot_shared.role_group_ownership import merge_declared_roles, warn_stale_detected_roles  # noqa: E402


def _node(declared, detected, node_id="n1"):
    return SimpleNamespace(node_id=node_id, roles=list(declared), detected_roles=list(detected))


def _groups(node):
    return ib._strip_undeclared_privileged_groups(node, ib.groups_for_role_tokens(*ib.declared_and_detected(node)))


def test_vnc_node_with_stale_postgres_does_not_join_redis():
    node = _node(["vnc", "slm-agent"], ["vnc", "slm-agent", "postgres", "slm-database"])
    assert not _groups(node) & {"redis", "database"}


def test_real_redis_host_still_joins_redis():
    node = _node(["slm-agent"], ["redis"])
    assert {"redis", "database"} <= _groups(node)


def test_detected_redis_alongside_postgres_still_joins_redis():
    node = _node(["slm-agent"], ["redis", "slm-database"])
    assert {"redis", "database"} <= _groups(node)


def test_declared_slm_database_keeps_full_mapping():
    node = _node(["slm-backend", "slm-database", "slm-monitoring"], ["slm-database", "postgres"])
    assert {"redis", "database", "monitoring_vm", "slm_server"} <= _groups(node)


def test_declared_postgres_keeps_database():
    assert "database" in _groups(_node(["postgres"], []))


def test_stale_detected_roles_are_surfaced_not_removed(caplog):
    node = _node(["vnc", "slm-agent"], ["postgres", "slm-database", "slm-agent"], node_id="vnc-node")
    with caplog.at_level("WARNING"):
        stale = warn_stale_detected_roles(node)
    assert stale == ["postgres", "slm-database"]
    assert node.detected_roles == ["postgres", "slm-database", "slm-agent"]
    assert "vnc-node" in caplog.text and "slm-database" in caplog.text


def test_stale_warning_names_withheld_groups_and_logs_once(caplog):
    node = _node(["vnc"], ["slm-database"], node_id="warn-once-node")
    with caplog.at_level("WARNING"):
        warn_stale_detected_roles(node, ib._role_tokens_to_groups)
        warn_stale_detected_roles(node, ib._role_tokens_to_groups)
    assert len(caplog.records) == 1
    assert "withheld" in caplog.text and "redis" in caplog.text and "no longer grants" not in caplog.text


def test_slm_self_registration_declares_its_own_roles_without_removing_any():
    slm_roles = ["slm-backend", "slm-frontend", "slm-database", "slm-monitoring"]
    merged = merge_declared_roles(["slm-backend", "custom"], slm_roles)
    assert merged == ["slm-backend", "custom", "slm-frontend", "slm-database", "slm-monitoring"]
    assert {"redis", "database"} <= _groups(_node(merged, ["slm-database"]))
    assert merge_declared_roles(None, slm_roles) == slm_roles
