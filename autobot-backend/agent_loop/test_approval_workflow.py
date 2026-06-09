# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for agent-loop approval workflow (Issue #4092).

Covers:
  - SENSITIVE_TOOLS classification (_sensitive_tool_name, _requires_approval)
  - _request_approval: publishes APPROVAL_REQUIRED, returns True when approved
  - _request_approval: returns False when denied
  - _request_approval: returns False on timeout
  - _check_approvals: skips non-sensitive tools
  - _check_approvals: returns error dict when tool is denied
  - _check_approvals: returns empty dict when all tools approved
  - _execute_tools: short-circuits on denied approval (no real execution)
  - AgentLoopConfig: approval fields have correct defaults
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.loop import SENSITIVE_TOOLS, AgentLoop
from agent_loop.types import AgentLoopConfig, LoopState, TaskContext
from events.types import EventType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str, args: Any = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"tool_name": name}
    if args is not None:
        spec["args"] = args
    return spec


def _make_loop(
    require_approval: bool = True,
    approval_timeout: int = 5,
) -> AgentLoop:
    """Return an AgentLoop wired with mock dependencies."""
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        require_approval_for_sensitive=require_approval,
        approval_timeout_seconds=approval_timeout,
    )
    loop = AgentLoop(event_stream=event_stream, config=config)
    loop._current_context = TaskContext(task_id="t-approval", description="test")
    loop._state = LoopState.RUNNING
    return loop


# ---------------------------------------------------------------------------
# SENSITIVE_TOOLS set
# ---------------------------------------------------------------------------


class TestSensitiveToolsSet:
    def test_known_sensitive_tools_present(self):
        for tool in ("bash", "write_file", "deploy", "git_push", "http_delete"):
            assert tool in SENSITIVE_TOOLS, f"Expected '{tool}' in SENSITIVE_TOOLS"

    def test_safe_tools_absent(self):
        for tool in ("read_file", "search", "list_directory", "think"):
            assert tool not in SENSITIVE_TOOLS, f"Did not expect '{tool}' in SENSITIVE_TOOLS"


# ---------------------------------------------------------------------------
# _sensitive_tool_name / _requires_approval
# ---------------------------------------------------------------------------


class TestSensitiveToolClassification:
    def test_exact_match(self):
        loop = _make_loop()
        assert loop._sensitive_tool_name(_make_tool("bash")) == "bash"

    def test_prefix_match(self):
        loop = _make_loop()
        # "bash_run" starts with "bash"
        assert loop._sensitive_tool_name(_make_tool("bash_run")) == "bash"

    def test_non_sensitive_returns_none(self):
        loop = _make_loop()
        assert loop._sensitive_tool_name(_make_tool("read_file")) is None

    def test_requires_approval_filters_correctly(self):
        loop = _make_loop()
        tools = [_make_tool("read_file"), _make_tool("write_file"), _make_tool("bash")]
        result = loop._requires_approval(tools)
        names = [t["tool_name"] for t in result]
        assert "write_file" in names
        assert "bash" in names
        assert "read_file" not in names

    def test_requires_approval_disabled(self):
        loop = _make_loop(require_approval=False)
        tools = [_make_tool("bash"), _make_tool("write_file")]
        assert loop._requires_approval(tools) == []


# ---------------------------------------------------------------------------
# _request_approval
# ---------------------------------------------------------------------------


class TestRequestApproval:
    @pytest.mark.asyncio
    async def test_approved_returns_true(self):
        loop = _make_loop()
        approval_id = "appr-001"

        # Simulate an APPROVAL_RESPONSE event that matches
        resp_event = MagicMock()
        resp_event.event_type = EventType.APPROVAL_RESPONSE
        resp_event.content = {"approval_id": approval_id, "approved": True}

        call_count = 0

        async def mock_get_latest(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return [resp_event]
            return []

        loop.event_stream.get_latest = mock_get_latest

        result = await loop._request_approval(_make_tool("bash"), approval_id)
        assert result is True
        loop.event_stream.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_denied_returns_false(self):
        loop = _make_loop()
        approval_id = "appr-002"

        resp_event = MagicMock()
        resp_event.event_type = EventType.APPROVAL_RESPONSE
        resp_event.content = {"approval_id": approval_id, "approved": False}

        loop.event_stream.get_latest = AsyncMock(return_value=[resp_event])
        result = await loop._request_approval(_make_tool("deploy"), approval_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        loop = _make_loop(approval_timeout=1)
        # Never provide a matching response
        loop.event_stream.get_latest = AsyncMock(return_value=[])
        result = await loop._request_approval(_make_tool("bash"), "appr-timeout")
        assert result is False

    @pytest.mark.asyncio
    async def test_unrelated_response_ignored(self):
        loop = _make_loop(approval_timeout=2)
        approval_id = "appr-003"

        unrelated = MagicMock()
        unrelated.event_type = EventType.APPROVAL_RESPONSE
        unrelated.content = {"approval_id": "other-id", "approved": True}

        matching = MagicMock()
        matching.event_type = EventType.APPROVAL_RESPONSE
        matching.content = {"approval_id": approval_id, "approved": True}

        call_count = 0

        async def mock_get_latest(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [unrelated]
            return [matching]

        loop.event_stream.get_latest = mock_get_latest
        result = await loop._request_approval(_make_tool("bash"), approval_id)
        assert result is True


# ---------------------------------------------------------------------------
# _check_approvals
# ---------------------------------------------------------------------------


class TestCheckApprovals:
    @pytest.mark.asyncio
    async def test_no_sensitive_tools_empty_result(self):
        loop = _make_loop()
        tools = [_make_tool("read_file"), _make_tool("search")]
        result = await loop._check_approvals(tools)
        assert result == {}
        loop.event_stream.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_approved_tool_empty_result(self):
        loop = _make_loop()

        async def approve_immediately(**kwargs):
            resp = MagicMock()
            resp.content = {
                "approval_id": kwargs.get("approval_id", ""),
                "approved": True,
            }
            return [resp]

        # Patch _request_approval to return True immediately
        loop._request_approval = AsyncMock(return_value=True)
        result = await loop._check_approvals([_make_tool("bash")])
        assert result == {}

    @pytest.mark.asyncio
    async def test_denied_tool_returns_error(self):
        loop = _make_loop()
        loop._request_approval = AsyncMock(return_value=False)
        result = await loop._check_approvals([_make_tool("bash")])
        assert "bash" in result
        assert "error" in result["bash"]
        assert "denied" in result["bash"]["error"]

    @pytest.mark.asyncio
    async def test_second_tool_skipped_after_denial(self):
        loop = _make_loop()
        loop._request_approval = AsyncMock(return_value=False)
        tools = [_make_tool("bash"), _make_tool("deploy")]
        result = await loop._check_approvals(tools)
        # Only one call — second tool never reached
        assert loop._request_approval.call_count == 1
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _execute_tools integration
# ---------------------------------------------------------------------------


class TestExecuteToolsApprovalGate:
    @pytest.mark.asyncio
    async def test_denied_tool_skips_execution(self):
        loop = _make_loop()
        loop._check_approvals = AsyncMock(return_value={"bash": {"error": "Tool 'bash' was denied by the user"}})
        result = await loop._execute_tools([_make_tool("bash")])
        assert "bash" in result
        assert "error" in result["bash"]

    @pytest.mark.asyncio
    async def test_approved_proceeds_to_execution(self):
        loop = _make_loop()
        loop._check_approvals = AsyncMock(return_value={})
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._think_before_tools = AsyncMock()
        loop._dispatch_tool = AsyncMock(return_value={"status": "executed"})
        result = await loop._execute_tools([_make_tool("bash")])
        assert result.get("bash") == {"status": "executed"}


# ---------------------------------------------------------------------------
# AgentLoopConfig defaults
# ---------------------------------------------------------------------------


class TestAgentLoopConfigDefaults:
    def test_approval_defaults(self):
        cfg = AgentLoopConfig()
        assert cfg.require_approval_for_sensitive is True
        assert cfg.approval_timeout_seconds == 300
