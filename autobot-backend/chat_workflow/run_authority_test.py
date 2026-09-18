# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a delegated run inherits from its parent, on both engines and at the forbidden-work seam (#16950)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow import delegation
from chat_workflow.models import AgentContext
from chat_workflow.run_authority import NO_INHERITANCE, Inheritance, authority_of, gated_tools
from chat_workflow.tool_dispatch_guards import enforce_forbidden_work
from security.authority import Authority


def _run(agent_id=None, gates=(), work_item=None, authority=None):
    return SimpleNamespace(
        agent_context=AgentContext(agent_id=agent_id, session_id="s") if agent_id else None,
        requires_approval_before=list(gates),
        work_item_id=work_item,
        authority=authority,
    )


class TestAuthorityOf:
    def test_a_run_holds_its_own_gates_and_profile_boundary(self):
        from orchestration.agent_registry import resolve_forbidden_tools

        authority = authority_of(_run("research_agent", gates=["writing files"]))

        assert authority.approval_gates == {"writing files"}
        assert authority.forbidden_tools == resolve_forbidden_tools("research_agent")

    def test_what_a_run_inherited_binds_it_too(self):
        inherited = Authority(forbidden_tools=frozenset({"http_get"}), approval_gates=frozenset({"publishing"}))

        authority = authority_of(_run("research_agent", authority=inherited))

        assert "http_get" in authority.forbidden_tools
        assert "publishing" in authority.approval_gates

    def test_no_parent_inherits_nothing(self):
        assert Inheritance.of(None) == NO_INHERITANCE

    def test_the_parents_work_item_is_inherited(self):
        assert Inheritance.of(_run("research_agent", work_item="wi-1")).work_item_id == "wi-1"


def test_gated_tools_are_the_categories_tools():
    assert {"write_file", "edit_file"} <= gated_tools(["writing files"])
    assert gated_tools(["not a category"]) == frozenset()


class TestTheInheritedBoundaryHoldsAtTheSeam:
    def test_a_tool_the_parent_forbade_is_blocked_for_the_child(self):
        child = _run("research_agent", authority=Authority(forbidden_tools=frozenset({"http_get"})))
        results: list = []

        blocked = enforce_forbidden_work({"name": "http_get"}, child, results)

        assert blocked is not None and results[0]["forbidden_by_manifest"] is True

    def test_the_same_tool_is_allowed_without_the_inheritance(self):
        """Control: research_agent's own profile allows http_get, so the block above is the inheritance."""
        assert enforce_forbidden_work({"name": "http_get"}, _run("research_agent"), []) is None


class TestTheOutOfProcessEngine:
    """claude_code runs its own tool loop and cannot ask for approval, so a gated tool is refused there."""

    @staticmethod
    async def _disallowed(inherited: Inheritance) -> list:
        import services.execution.claude_code_backend as ccb

        result = SimpleNamespace(stdout="ok", stderr="")
        mock_exec = AsyncMock(return_value=result)
        with patch.object(ccb.ClaudeCodeBackend, "execute", new=mock_exec):
            await delegation._run_claude_code_subagent("subtask", "research_agent", 0, "user", inherited)
        return mock_exec.await_args.args[0].metadata["disallowed_tools"]

    @pytest.mark.asyncio
    async def test_a_gate_the_parent_holds_is_refused_to_the_child(self):
        inherited = Inheritance(authority=Authority(approval_gates=frozenset({"writing files"})))

        disallowed = await self._disallowed(inherited)

        assert {"Write", "Edit"} <= set(disallowed)

    @pytest.mark.asyncio
    async def test_without_the_gate_the_child_may_write(self):
        """Control: the Write and Edit above come from the parent's gate, not the child's profile."""
        disallowed = await self._disallowed(NO_INHERITANCE)

        assert "Write" not in disallowed and "Edit" not in disallowed


@pytest.mark.asyncio
async def test_the_internal_child_carries_the_parents_work_item_and_gates():
    captured = {}

    async def _fake_loop(ctx):
        captured["ctx"] = ctx
        yield ([], [], None)

    import chat_workflow

    inherited = Inheritance(authority=Authority(approval_gates=frozenset({"writing files"})), work_item_id="wi-7")
    manager = SimpleNamespace(_execute_llm_continuation_loop=_fake_loop)
    with patch.object(chat_workflow, "get_chat_workflow_manager", return_value=manager):
        await delegation._run_internal_subagent("t", "documentation_agent", 0, "user", inherited)

    child = captured["ctx"]
    assert child.work_item_id == "wi-7"
    assert "writing files" in child.requires_approval_before
    assert child.authority is inherited.authority
