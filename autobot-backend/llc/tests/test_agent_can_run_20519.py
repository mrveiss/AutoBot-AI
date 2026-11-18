# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent lists say whether an agent can run, from the dispatcher's own check (#20519)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from llc.api.agents import _agent_row
from llc.api.companies import _compose_agent_node
from llc.exceptions import HeartbeatDispatchSkipped
from llc.scheduler.dispatch_gate import adapter_block_reason, run_block_reason
from llc.scheduler.heartbeat_scheduler import _dispatch_autobot_agent

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
    assert run_block_reason("available", "autobot_agent", {"agent_class": "X"}, org_role="worker") is None


def test_unregistered_adapter_type_cannot_run():
    assert "no LLC adapter registered" in adapter_block_reason("no_such_adapter", {})


def test_paused_agent_cannot_run_and_names_the_status():
    assert (
        run_block_reason("paused", "autobot_agent", {"agent_class": "X"}, org_role="worker") == "agent status is paused"
    )


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


@pytest.mark.asyncio
async def test_in_process_dispatch_skips_with_the_shared_gate_answer():
    """Dispatch of an autobot_agent asks the one gate the lists ask, and keeps its text."""
    agent = {"agent_id": "a1", "adapter_type": "autobot_agent", "adapter_config": {}}
    with pytest.raises(HeartbeatDispatchSkipped) as real:
        await _dispatch_autobot_agent(agent, {})
    assert _NO_CLASS in str(real.value)
    target = "llc.scheduler.heartbeat_scheduler.adapter_block_reason"
    with patch(target, return_value="shared answer") as gate:
        with pytest.raises(HeartbeatDispatchSkipped) as shared:
            await _dispatch_autobot_agent(agent, {})
    gate.assert_called_once_with("autobot_agent", {})
    assert "shared answer" in str(shared.value)


@pytest.mark.parametrize("enforced", [True, False])
def test_list_says_an_agent_the_role_bound_refuses_cannot_run(enforced):
    """#20706: with the bound enforced, the list gives dispatch's refusal; with it off, the agent runs."""
    from llc.org_role_authority import _no_bound_reason

    with patch("llc.org_role_authority.is_feature_enabled", return_value=enforced):
        row = _agent_row(_node("Alex", org_role=None), None)
        node = _compose_agent_node(_node("Alex", org_role=None), None, None, 0)
    if enforced:
        expected = f"{_no_bound_reason(None)} (#16950)"
        assert (row["can_run"], row["cannot_run_reason"]) == (False, expected)
        assert (node.can_run, node.cannot_run_reason) == (False, expected)
    else:
        assert (row["can_run"], row["cannot_run_reason"]) == (True, None)
        assert (node.can_run, node.cannot_run_reason) == (True, None)
