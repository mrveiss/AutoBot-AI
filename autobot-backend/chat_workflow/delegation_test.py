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
    from chat_workflow.delegation import _claude_tool_for
    from orchestration.agent_registry import resolve_forbidden_tools

    forbidden = resolve_forbidden_tools("research_agent")
    assert forbidden, "research_agent must declare forbidden_work"
    unmapped = sorted(t for t in forbidden if _claude_tool_for(t) is None)
    assert unmapped == [], f"forbidden tokens with no claude_code mapping (fail-open): {unmapped}"


def test_claude_tool_mapping_derived_from_canonical_atoms():
    # No duplicated token lists: the mapping must cover every shell/infra/terminal/
    # delete atom (→ Bash) and the file-write atoms (Write/Edit/Bash) from tool_catalogue.
    from autobot_shared import tool_catalogue as tc
    from chat_workflow.delegation import _claude_tool_for

    for token in tc.INFRA_AND_SHELL_TOOLS + tc.TERMINAL_TOOLS + tc.FILE_DELETE_TOOLS:
        assert _claude_tool_for(token) == "Bash", token
    assert _claude_tool_for("write_file") == "Write"
    assert _claude_tool_for("edit_file") == "Edit"
    for token in set(tc.FILE_WRITE_TOOLS) - {"write_file", "edit_file"}:
        assert _claude_tool_for(token) == "Bash", token


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


# --- internal-LLM engine ---------------------------------------------------


@pytest.mark.asyncio
async def test_internal_engine_governs_and_bounds_depth():
    # The internal engine drives the production loop with a governed ctx: agent_id
    # set (→ forbidden_work enforced at the seam) and delegation_depth incremented
    # (→ an in-loop delegate is bounded). It returns the joined LLM responses.
    captured = {}

    async def _fake_loop(ctx):
        captured["ctx"] = ctx
        yield ("progress message — ignored")  # non-tuple stream item
        yield (["part one", "", "part two"], [], None)  # final (responses, history, error)

    import chat_workflow

    fake_mgr = type("M", (), {"_execute_llm_continuation_loop": staticmethod(_fake_loop)})()
    with patch.object(chat_workflow, "get_chat_workflow_manager", return_value=fake_mgr):
        out = await delegation._run_internal_subagent("do the thing", "research_agent", 1)

    assert out == "part one\npart two"  # empty parts dropped, rest joined
    ctx = captured["ctx"]
    assert ctx.agent_context is not None and ctx.agent_context.agent_id == "research_agent"
    assert ctx.context["delegation_depth"] == 2  # depth 1 → subagent sees 2
    assert ctx.initial_prompt == "do the thing"


@pytest.mark.asyncio
async def test_internal_engine_registered_and_dispatches():
    engine = AsyncMock(return_value="internal result")
    with patch.dict(delegation._ENGINES, {"internal": engine}):
        out = await run_delegated_subtask("t", agent_type="research_agent", depth=0, engine="internal")
    assert out == "internal result"
    engine.assert_awaited_once_with("t", "research_agent", 0)


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
