# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Governed subagent delegation runner (GH#11207)."""

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow import delegation
from chat_workflow.delegation import (
    MAX_DELEGATION_DEPTH,
    forbidden_to_claude_tools,
    run_delegated_subtask,
)

# --- forbidden_work → claude_code tool mapping -----------------------------


def test_forbidden_to_claude_tools_maps_and_dedups():
    out = forbidden_to_claude_tools(["bash", "execute_command", "write_file", "edit_file"])
    assert out == ["Bash", "Edit", "Write"]  # bash+execute_command → single Bash, sorted


def test_forbidden_to_claude_tools_ignores_unmapped():
    assert forbidden_to_claude_tools(["totally_unknown_tool"]) == []


def test_shipped_research_agent_has_no_fail_open_tokens():
    # Governance guard: every token the shipped research_agent forbids must map to a
    # claude_code --disallowedTools entry, so nothing silently fails open.
    from chat_workflow.delegation import _CLAUDE_TOOL_FOR
    from orchestration.agent_registry import resolve_forbidden_tools

    forbidden = resolve_forbidden_tools("research_agent")
    assert forbidden, "research_agent must declare forbidden_work"
    unmapped = sorted(t for t in forbidden if t not in _CLAUDE_TOOL_FOR)
    assert unmapped == [], f"forbidden tokens with no claude_code mapping (fail-open): {unmapped}"


# --- run_delegated_subtask dispatch + guards -------------------------------


@pytest.mark.asyncio
async def test_run_delegated_subtask_depth_guard():
    with pytest.raises(ValueError):
        await run_delegated_subtask("t", depth=MAX_DELEGATION_DEPTH)


@pytest.mark.asyncio
async def test_run_delegated_subtask_unknown_engine():
    with pytest.raises(ValueError):
        await run_delegated_subtask("t", engine="not_an_engine")


@pytest.mark.asyncio
async def test_run_delegated_subtask_dispatches_to_engine():
    engine = AsyncMock(return_value="subagent output")
    with patch.dict(delegation._ENGINES, {"claude_code": engine}):
        out = await run_delegated_subtask("do it", agent_type="research_agent", depth=0)
    assert out == "subagent output"
    engine.assert_awaited_once_with("do it", "research_agent", 0)


@pytest.mark.asyncio
async def test_claude_code_engine_passes_disallowed_from_forbidden_work():
    # research_agent forbids infra/shell tools → they map to Bash on the CLI.
    import services.execution.claude_code_backend as ccb

    result = type("R", (), {"stdout": "ok", "stderr": ""})()
    mock_exec = AsyncMock(return_value=result)
    with patch.object(ccb.ClaudeCodeBackend, "execute", new=mock_exec):
        out = await delegation._run_claude_code_subagent("subtask", "research_agent", 0)
    assert out == "ok"
    task = mock_exec.await_args.args[0]  # Mock class-attr is not bound → self not passed
    assert "Bash" in task.metadata["disallowed_tools"]


# --- _handle_delegate_tool: flag off = unchanged, on = runs subagent -------


def _mixin():
    from chat_workflow.tool_handler import ToolHandlerMixin

    return ToolHandlerMixin.__new__(ToolHandlerMixin)


@pytest.mark.asyncio
async def test_delegate_tool_off_records_pending_delegation():
    mixin = _mixin()
    results = []
    with patch.object(delegation, "DELEGATION_ENABLED", False):
        msgs = [m async for m in mixin._handle_delegate_tool({"params": {"task": "x"}}, results, None)]
    assert results[0]["status"] == "pending_delegation"
    assert msgs[0].type == "delegation"


@pytest.mark.asyncio
async def test_delegate_tool_on_runs_governed_subagent():
    mixin = _mixin()
    results = []
    with (
        patch.object(delegation, "DELEGATION_ENABLED", True),
        patch.object(delegation, "run_delegated_subtask", new=AsyncMock(return_value="done")),
    ):
        msgs = [
            m
            async for m in mixin._handle_delegate_tool(
                {"params": {"task": "x", "agent_type": "research_agent"}}, results, None
            )
        ]
    assert results[0]["status"] == "completed" and results[0]["result"] == "done"
    assert msgs[0].type == "delegation"
