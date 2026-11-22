# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-node health of multi-node roles (#19706)."""

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "_role_nodes_under_test", Path(__file__).parents[2] / "services" / "role_nodes.py"
)
role_nodes = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(role_nodes)


def _row(hostname, status="active", node_status="online", role="npu-worker"):
    return SimpleNamespace(role_name=role, hostname=hostname, status=status, node_status=node_status)


def _health(health="healthy", detail="All roles active"):
    return SimpleNamespace(
        health=health, detail=detail, model_copy=lambda update: SimpleNamespace(**{"health": health, **update})
    )


def test_all_nodes_up_reports_nothing():
    assert role_nodes.classify_role_nodes([_row("a"), _row("b")]) == []


def test_an_offline_node_is_down_and_the_others_stay_up():
    result = role_nodes.classify_role_nodes([_row("a"), _row("b", node_status="offline")])
    assert [(r.role, r.nodes_up, r.nodes_down) for r in result] == [("npu-worker", ["a"], ["b"])]


def test_an_inactive_service_on_an_online_node_is_down():
    result = role_nodes.classify_role_nodes([_row("a", status="inactive"), _row("b")])
    assert result[0].nodes_down == ["a"]


def test_a_node_not_installed_yet_is_neither_up_nor_down():
    result = role_nodes.classify_role_nodes([_row("a", status="not_installed", node_status="offline"), _row("b")])
    assert result == []


@pytest.mark.parametrize("node_status", ["decommissioned", "maintenance", "pending", "enrolling"])
def test_a_node_not_serving_by_plan_is_neither_up_nor_down(node_status):
    rows = [_row("a", node_status=node_status), _row("b", node_status="offline")]
    result = role_nodes.classify_role_nodes(rows)
    assert (result[0].nodes_up, result[0].nodes_down) == ([], ["b"])


def test_every_node_down_is_still_reported():
    result = role_nodes.classify_role_nodes([_row("a", node_status="error")])
    assert (result[0].nodes_up, result[0].nodes_down) == ([], ["a"])


def test_a_node_down_degrades_a_healthy_fleet_and_names_the_node():
    down = role_nodes.classify_role_nodes([_row("a"), _row("b", node_status="offline")])
    result = role_nodes.with_nodes_down(_health(), down)
    assert result.health == "degraded"
    assert result.detail == "Degraded: npu-worker down on b (1 of 2 nodes)"
    assert result.roles_with_nodes_down == down


def test_a_critical_fleet_stays_critical_and_keeps_its_detail():
    down = role_nodes.classify_role_nodes([_row("b", node_status="offline")])
    result = role_nodes.with_nodes_down(_health("critical", "Critical: redis"), down)
    assert result.health == "critical"
    assert result.detail == "Critical: redis; npu-worker down on b (1 of 1 nodes)"


def test_no_roles_down_returns_the_same_health():
    health = _health()
    assert role_nodes.with_nodes_down(health, []) is health


def test_only_roles_whose_traffic_can_spread_carry_the_flag():
    """Flag a role only once its consumers can reach every node, or a second node gets no traffic."""
    source = (Path(__file__).parents[2] / "services" / "role_registry.py").read_text(encoding="utf-8")
    flagged = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            if "multi_node" in fields and fields["multi_node"].value is True:
                flagged.add(fields["name"].value)
    assert flagged == {"autobot_shared", "slm-agent"}
