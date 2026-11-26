# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Governed subagent delegation runner (GH#11207, GH#11266)."""

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow import delegation
from chat_workflow.delegation import (
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TURN,
    forbidden_to_claude_tools,
    run_delegated_subtask,
)
from chat_workflow.models import AgentContext
from chat_workflow.run_authority import NO_INHERITANCE

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
async def test_depth_guard_tells_the_model_what_to_do_instead():
    with pytest.raises(ValueError, match="complete this task directly instead of delegating further"):
        await run_delegated_subtask("t", depth=MAX_DELEGATION_DEPTH)


@pytest.mark.asyncio
async def test_run_delegated_subtask_logs_elapsed_time(caplog):
    engine = AsyncMock(return_value="ok")
    with patch.dict(delegation._ENGINES, {"claude_code": engine}), caplog.at_level("INFO"):
        await run_delegated_subtask("t")
    assert any("delegation done" in r.getMessage() and "elapsed=" in r.getMessage() for r in caplog.records)


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
    engine.assert_awaited_once_with("do it", "research_agent", 0, "user", NO_INHERITANCE)


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
    engine.assert_awaited_once_with("t", "research_agent", 0, "user", NO_INHERITANCE)


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


# --- GH#11266: env_flag / env_int usage (canonical truthy set) ---------------


def test_delegation_enabled_default_is_false():
    """DELEGATION_ENABLED must default OFF — no side-effects on import."""

    # Reload with env cleared to confirm default.
    saved = delegation.DELEGATION_ENABLED
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("AUTOBOT_DELEGATION_ENABLED", None)
        # Re-evaluate the flag via env_flag to confirm semantics.
        from autobot_shared.env_utils import env_flag

        assert env_flag("AUTOBOT_DELEGATION_ENABLED", default=False) is False
    # Module-level constant must also be False (loaded without the env var set).
    assert saved is False, "DELEGATION_ENABLED must be OFF by default"


def test_max_delegation_depth_from_env_int():
    """MAX_DELEGATION_DEPTH is read via env_int so invalid values fall back gracefully."""
    from autobot_shared.env_utils import env_int

    assert env_int("AUTOBOT_MAX_DELEGATION_DEPTH", default=2) == MAX_DELEGATION_DEPTH


def test_max_delegations_per_turn_exported():
    """MAX_DELEGATIONS_PER_TURN constant is exported and positive."""
    assert MAX_DELEGATIONS_PER_TURN > 0


# --- GH#11266: run_delegated_subtask — parent_agent_id observability ---------


@pytest.mark.asyncio
async def test_run_delegated_subtask_logs_parent_agent_id(caplog):
    """Dispatch must emit an INFO log containing parent_agent_id."""
    import logging

    engine = AsyncMock(return_value="result")
    with patch.dict(delegation._ENGINES, {"claude_code": engine}):
        with caplog.at_level(logging.INFO, logger="chat_workflow.delegation"):
            await run_delegated_subtask("task", agent_type="research_agent", depth=0, parent_agent_id="root_agent")
    assert any("root_agent" in r.message for r in caplog.records), "parent_agent_id must appear in INFO log"
    assert any("research_agent" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_run_delegated_subtask_logs_the_parent_runs_agent_id(caplog):
    """#16950: the delegate handler passes the parent run; its agent_id must still reach the log."""
    import logging
    from types import SimpleNamespace

    parent = SimpleNamespace(agent_context=SimpleNamespace(agent_id="the_parent"))
    engine = AsyncMock(return_value="result")
    with patch.dict(delegation._ENGINES, {"claude_code": engine}):
        with caplog.at_level(logging.INFO, logger="chat_workflow.delegation"):
            await run_delegated_subtask("task", agent_type="research_agent", depth=0, parent=parent)
    assert any("parent=the_parent" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_run_delegated_subtask_logs_root_when_no_parent(caplog):
    """When parent_agent_id is None the log must show 'root'."""
    import logging

    engine = AsyncMock(return_value="result")
    with patch.dict(delegation._ENGINES, {"claude_code": engine}):
        with caplog.at_level(logging.INFO, logger="chat_workflow.delegation"):
            await run_delegated_subtask("task", depth=0)
    assert any("root" in r.message for r in caplog.records)


# --- GH#11266: per-turn delegation fan-out limit ----------------------------


@pytest.mark.asyncio
async def test_delegate_tool_per_turn_limit_blocks_excess():
    """After MAX_DELEGATIONS_PER_TURN calls the next one is rejected with an error."""
    from types import SimpleNamespace

    mixin = _mixin()
    # Fabricate a minimal ctx with context dict already at limit.
    ctx = SimpleNamespace(
        context={"delegations_this_turn": MAX_DELEGATIONS_PER_TURN},
        agent_context=None,
    )
    results = []
    with patch.object(delegation, "DELEGATION_ENABLED", True):
        msgs = [m async for m in mixin._handle_delegate_tool({"params": {"task": "overflow"}}, results, ctx)]
    assert results[0]["status"] == "error"
    assert "limit" in results[0]["error"]
    assert msgs[0].type == "error"


@pytest.mark.asyncio
async def test_delegate_tool_per_turn_counter_increments():
    """Each successful delegation increments delegations_this_turn on ctx."""
    from types import SimpleNamespace

    mixin = _mixin()
    ctx = SimpleNamespace(context={"delegations_this_turn": 0}, agent_context=None)
    results = []
    with (
        patch.object(delegation, "DELEGATION_ENABLED", True),
        patch.object(delegation, "run_delegated_subtask", new=AsyncMock(return_value="ok")),
    ):
        _ = [m async for m in mixin._handle_delegate_tool({"params": {"task": "t"}}, results, ctx)]
    assert ctx.context["delegations_this_turn"] == 1


@pytest.mark.asyncio
async def test_delegate_tool_passes_parent_agent_id_to_runner():
    """The parent run, and so its agent_id, must reach run_delegated_subtask."""
    from types import SimpleNamespace

    mixin = _mixin()
    agent_ctx = SimpleNamespace(agent_id="the_parent")
    ctx = SimpleNamespace(
        context={"delegations_this_turn": 0, "delegation_depth": 0}, agent_context=agent_ctx, auth_role="admin"
    )
    captured = {}
    mock_run = AsyncMock(side_effect=lambda *a, **kw: captured.update(kw) or "done")

    with (
        patch.object(delegation, "DELEGATION_ENABLED", True),
        patch.object(delegation, "run_delegated_subtask", new=mock_run),
    ):
        _ = [m async for m in mixin._handle_delegate_tool({"params": {"task": "t"}}, [], ctx)]
    # #16950: the handler passes the parent run itself, not just its id, so the child
    # can inherit its authority; run_delegated_subtask reads the id from it for the log.
    assert captured["parent"].agent_context.agent_id == "the_parent"
    # #13821: a subagent acts for the same authenticated user. Dropping the role
    # here would deny an admin the tools they are entitled to, the moment
    # delegation ships.
    assert captured.get("auth_role") == "admin"


# --- GH#11266: env_flag covers "on" (canonical truthy) ----------------------


def test_env_flag_covers_on_truthy():
    """env_flag('AUTOBOT_DELEGATION_ENABLED') must accept 'on' as truthy."""
    from autobot_shared.env_utils import env_flag

    with patch.dict("os.environ", {"AUTOBOT_DELEGATION_ENABLED": "on"}):
        assert env_flag("AUTOBOT_DELEGATION_ENABLED") is True

    with patch.dict("os.environ", {"AUTOBOT_DELEGATION_ENABLED": "yes"}):
        assert env_flag("AUTOBOT_DELEGATION_ENABLED") is True

    with patch.dict("os.environ", {"AUTOBOT_DELEGATION_ENABLED": "1"}):
        assert env_flag("AUTOBOT_DELEGATION_ENABLED") is True

    with patch.dict("os.environ", {"AUTOBOT_DELEGATION_ENABLED": "false"}):
        assert env_flag("AUTOBOT_DELEGATION_ENABLED") is False


# --- AgentContext hierarchy (moved from the retired subordinate_delegation_test, #21687) ---


class TestAgentContext:
    """Test AgentContext dataclass functionality."""

    def test_default_creation(self):
        """Test default context creation."""
        ctx = AgentContext(agent_id="test-agent")
        assert ctx.agent_id == "test-agent"
        assert ctx.level == 0
        assert ctx.parent_id is None
        assert ctx.max_depth == 3
        assert ctx.can_delegate() is True

    def test_root_can_delegate(self):
        """Root agent should be able to delegate."""
        ctx = AgentContext(agent_id="root", level=0)
        assert ctx.can_delegate() is True

    def test_at_max_depth_cannot_delegate(self):
        """Agent at max depth should not be able to delegate."""
        ctx = AgentContext(agent_id="deep", level=3, max_depth=3)
        assert ctx.can_delegate() is False

    def test_create_subordinate_context(self):
        """create_subordinate_context should create proper child context."""
        parent = AgentContext(agent_id="parent", level=0, session_id="session-123")
        child = parent.create_subordinate_context("child-id")

        assert child.agent_id == "child-id"
        assert child.level == 1
        assert child.parent_id == "parent"
        assert child.session_id == "session-123"
        assert child.max_depth == 3  # Inherited

    def test_create_subordinate_at_max_depth_raises(self):
        """Creating subordinate at max depth should raise ValueError."""
        ctx = AgentContext(agent_id="deep", level=3, max_depth=3)

        with pytest.raises(ValueError, match="Cannot delegate"):
            ctx.create_subordinate_context("child")

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        ctx = AgentContext(
            agent_id="test",
            level=1,
            parent_id="parent",
            max_depth=5,
            session_id="session",
        )
        d = ctx.to_dict()

        assert d["agent_id"] == "test"
        assert d["level"] == 1
        assert d["parent_id"] == "parent"
        assert d["max_depth"] == 5
        assert d["session_id"] == "session"
        assert d["can_delegate"] is True
