# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A Company OS run is bounded by its org role, or refused with the reason (#16950).

The owner approved the role table and decided each adapter: claude_code maps the
role through the fixed translation (a Bash-keeping role's shell-reachable limits
are accepted as unenforced, and listed); an adapter with no tool-permission flags
refuses a bounded role; the in-process adapter attributes the run to the org agent.
"""

import inspect
from unittest.mock import patch

import pytest

from llc.exceptions import HeartbeatDispatchSkipped
from llc.org_role_authority import (
    ORG_ROLE_AUTHORITY,
    apply_org_role_bound,
    claude_code_bound,
    describe_role_bound,
    org_role_authority,
)
from models.agent_org import OrgRole


def _agent(role="manager", adapter="claude_code", config=None):
    return {"agent_id": "agent-1", "org_role": role, "adapter_type": adapter, "adapter_config": config or {}}


class TestTheTable:
    def test_every_org_role_has_an_approved_bound(self):
        """A role added to the enum without a row would be refused on every run -- fail here instead."""
        assert set(ORG_ROLE_AUTHORITY) == {role.value for role in OrgRole}

    @pytest.mark.parametrize("role", [None, "", "ceo"])
    def test_a_role_without_a_row_is_refused_not_run_unbounded(self, role):
        with pytest.raises(ValueError):
            org_role_authority(role)


class TestClaudeCodeMapping:
    @pytest.mark.parametrize("role", ["manager", "coordinator"])
    def test_a_hands_off_role_loses_bash_and_every_limit_is_enforced(self, role):
        disallowed, unenforced = claude_code_bound(org_role_authority(role))

        assert {"Bash", "Write", "Edit"} <= set(disallowed)
        assert unenforced == []

    @pytest.mark.parametrize("role", ["specialist", "worker"])
    def test_a_hands_on_role_keeps_bash_and_its_gap_is_listed(self, role):
        """Owner decision: the Bash gap is accepted for org roles, and stated, not hidden."""
        disallowed, unenforced = claude_code_bound(org_role_authority(role))

        assert "Bash" not in disallowed
        assert {"git_push", "http_post", "deploy"} <= set(unenforced)

    def test_the_worker_lists_what_it_adds(self):
        _, unenforced = claude_code_bound(org_role_authority("worker"))

        assert {"rotate_credentials", "code_interpreter"} <= set(unenforced)


class TestAdapters:
    @pytest.mark.parametrize("adapter", ["claude_code", "claude_code_subscription", "autobot_agent", None])
    def test_an_adapter_that_can_carry_the_bound_runs(self, adapter):
        assert describe_role_bound("worker", adapter)["runs"] is True

    @pytest.mark.parametrize("adapter", ["copilot_local", "copilot_subscription", "codex_subscription"])
    def test_an_adapter_with_no_tool_flags_refuses_a_bounded_role(self, adapter):
        view = describe_role_bound("worker", adapter)

        assert view["runs"] is False and "no tool-permission flags" in view["reason"]


def test_every_registered_adapter_has_a_decision():
    """A new adapter must be classified before it can run a bounded role."""
    from llc.adapters import registered_adapter_types
    from llc.org_role_authority import CLASSIFIED_ADAPTERS

    assert set(registered_adapter_types()) <= CLASSIFIED_ADAPTERS


class TestApplyAtDispatch:
    def test_a_claude_code_run_carries_the_roles_disallowed_tools(self):
        bounded = apply_org_role_bound(_agent("manager", config={"disallowed_tools": ["WebFetch"]}))

        tools = set(bounded["adapter_config"]["disallowed_tools"])
        assert {
            "Bash",
            "Write",
            "Edit",
            "WebFetch",
        } <= tools, "the role adds to the agent's own config, never replaces it"
        assert bounded["adapter_config"]["unenforced_role_bound"] == []

    def test_a_bash_keeping_run_records_what_is_unenforced(self):
        bounded = apply_org_role_bound(_agent("specialist"))

        assert "Bash" not in bounded["adapter_config"]["disallowed_tools"]
        assert "git_push" in bounded["adapter_config"]["unenforced_role_bound"]

    def test_an_unenforceable_adapter_is_refused_with_the_reason(self):
        with pytest.raises(HeartbeatDispatchSkipped, match="#16950"):
            apply_org_role_bound(_agent("worker", adapter="copilot_local"))

    def test_a_run_with_no_role_is_refused(self):
        with pytest.raises(HeartbeatDispatchSkipped):
            apply_org_role_bound(_agent(None))

    def test_the_in_process_adapter_runs_unchanged(self):
        agent = _agent("worker", adapter="autobot_agent")

        assert apply_org_role_bound(agent) is agent


@pytest.mark.asyncio
async def test_the_scheduler_refuses_before_any_adapter_is_resolved():
    """The real dispatch point: every heartbeat and comment-wake run passes it."""
    from llc.scheduler import heartbeat_scheduler

    with patch.object(heartbeat_scheduler, "get_adapter") as get_adapter:
        with pytest.raises(HeartbeatDispatchSkipped):
            await heartbeat_scheduler._dispatch_adapter(_agent("worker", adapter="copilot_local"), {})

    get_adapter.assert_not_called()


def test_both_dispatch_sources_carry_the_role():
    """A source that drops org_role would have every run refused: pin that both load it."""
    from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler
    from llc.services.comment_wake_service import CommentWakeService

    assert "aon.org_role" in inspect.getsource(HeartbeatScheduler._load_enabled_agents)
    assert '"org_role": agent_row.get("org_role")' in inspect.getsource(CommentWakeService)


def test_an_in_process_run_is_attributed_to_the_org_agent():
    """#16946 owner decision 2: the originator of an autonomous run is the org agent itself."""
    from llc.adapters.autobot_agent_adapter import _build_agent_request

    request = _build_agent_request("run-1", {"agent_id": "agent-1", "title": "t"})

    assert (request.originator, request.chain) == ("agent-1", ["agent-1"])
