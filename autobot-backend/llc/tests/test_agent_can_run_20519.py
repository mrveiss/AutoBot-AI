# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent lists say whether an agent can run, from the dispatcher's own check (#20519)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from llc.api.agents import _agent_row
from llc.api.companies import _compose_agent_node
from llc.scheduler.dispatch_gate import adapter_block_reason, run_block_reason

_NO_CLASS = "no adapter_config.agent_class configured"


def _node(name: str, **overrides):
    values = {
        "id": uuid.uuid4(),
        "agent_id": f"slug-{uuid.uuid4().hex[:6]}",
        "name": name,
        "org_role": "worker",
        "title": "Engineer",
        "status": "available",
        "adapter_type": "autobot_agent",
        "adapter_config": {"agent_class": "ResearchAgent"},
        "heartbeat_enabled": True,
        "last_heartbeat_at": None,
        "reports_to": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_autobot_agent_without_agent_class_cannot_run():
    """The default CEO shape (#20507): a provisioned row with no agent_class."""
    assert adapter_block_reason(None, {}) == _NO_CLASS
    assert adapter_block_reason("autobot_agent", None) == _NO_CLASS


def test_configured_autobot_agent_can_run():
    assert run_block_reason("available", "autobot_agent", {"agent_class": "X"}) is None


def test_unregistered_adapter_type_cannot_run():
    assert "no LLC adapter registered" in adapter_block_reason("no_such_adapter", {})


def test_paused_agent_cannot_run_and_names_the_status():
    assert run_block_reason("paused", "autobot_agent", {"agent_class": "X"}) == "agent status is paused"


def test_list_rows_for_same_named_agents_differ_in_identity_and_run_state():
    runner = _node("Alex")
    idle = _node("Alex", adapter_config={})
    rows = [_agent_row(runner, None), _agent_row(idle, None)]
    assert rows[0]["name"] == rows[1]["name"] == "Alex"
    assert rows[0]["org_node_id"] != rows[1]["org_node_id"]
    assert (rows[0]["can_run"], rows[0]["cannot_run_reason"]) == (True, None)
    assert (rows[1]["can_run"], rows[1]["cannot_run_reason"]) == (False, _NO_CLASS)
    assert rows[1]["adapter_type"] == "autobot_agent"


def test_org_chart_node_carries_the_same_fact():
    node = _compose_agent_node(_node("Alex", adapter_config={}), None, None, 0)
    assert (node.can_run, node.cannot_run_reason) == (False, _NO_CLASS)
    ok = _compose_agent_node(_node("Alex"), None, None, 0)
    assert (ok.can_run, ok.cannot_run_reason) == (True, None)
