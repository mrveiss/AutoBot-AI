# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Learned auto-approve rules are part of the single AI-line decision (#16840).

One rule set, scoped to the user who created it, read through ``resolve_action_line`` by BOTH the chat tool
seam and the agent terminal. A rule only lifts a line-2 SAFE or MODERATE command; a destructive or
unknown-risk command always asks, and line 3 is never lifted.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ai_lines import AiLine
from autobot_shared.status_enums import CommandRisk
from chat_workflow.tool_dispatch_guards import COMMAND_FORCE_APPROVAL_KEY, enforce_ai_line
from services import ai_line_enforcement as enforcement
from services.agent_terminal.ai_line_gate import decide_command
from services.ai_line_enforcement import resolve_action_line
from services.command_approval_manager import CommandApprovalManager

pytestmark = pytest.mark.asyncio

_CREATOR = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_RISK = "services.command_line_risk.assess_command_risk"
_MANAGER = "services.command_line_risk.shared_approval_manager"
_COMMAND = "touch notes.txt"


async def _manager_with_rule(risk: CommandRisk = CommandRisk.MODERATE) -> CommandApprovalManager:
    manager = CommandApprovalManager()
    await manager.store_auto_approve_rule(_CREATOR, _COMMAND, risk.value)
    return manager


def _env(risk: CommandRisk | None, manager: CommandApprovalManager, stored: AiLine | None = None):
    """The resolver's inputs: no stored line (unless given), no baseline floor, a fixed risk, one rule set."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch.object(enforcement, "_stored", AsyncMock(return_value=(stored, False))))
    stack.enter_context(
        patch("chat_workflow.approval_baseline.baseline_approval_categories", AsyncMock(return_value=[]))
    )
    stack.enter_context(patch(_RISK, return_value=risk))
    stack.enter_context(patch(_MANAGER, return_value=manager))
    return stack


async def _line(user_id, risk=CommandRisk.MODERATE, manager=None, stored=None, **kwargs) -> AiLine:
    with _env(risk, manager or await _manager_with_rule(), stored):
        resolution = await resolve_action_line(
            "execute_command", {"command": _COMMAND}, None, user_id=user_id, **kwargs
        )
    return resolution.line


async def test_a_rule_matched_command_runs_unheld_for_its_creator():
    assert await _line(_CREATOR) is AiLine.AUTONOMOUS


async def test_another_user_still_gets_the_card():
    assert await _line(_OTHER) is AiLine.DRAFT_THEN_SEND


@pytest.mark.parametrize("risk", [CommandRisk.HIGH, CommandRisk.DANGEROUS, CommandRisk.CRITICAL, None])
async def test_a_destructive_or_unknown_risk_command_matching_a_rule_is_still_held(risk):
    manager = await _manager_with_rule(risk or CommandRisk.MODERATE)
    assert await _line(_CREATOR, risk=risk, manager=manager) is AiLine.DRAFT_THEN_SEND


async def test_line_3_is_never_lifted_by_a_rule():
    assert await _line(_CREATOR, stored=AiLine.NEVER) is AiLine.NEVER


async def test_the_attachment_floor_is_not_lifted_by_a_rule():
    assert await _line(_CREATOR, role_requires_approval=True, learned_rules_apply=False) is AiLine.DRAFT_THEN_SEND


async def _chat_call(user_id):
    tool_call = {"name": "execute_command", "params": {"command": _COMMAND}}
    ctx = SimpleNamespace(context={"verified_user_id": user_id}, session_id="chat-1", requires_approval_before=[])
    with _env(CommandRisk.MODERATE, await _manager_with_rule()), patch.object(enforcement, "_report", AsyncMock()):
        assert await enforce_ai_line(tool_call, ctx, []) is None
    return tool_call


async def test_chat_runs_the_creators_rule_matched_command_unheld():
    assert COMMAND_FORCE_APPROVAL_KEY not in await _chat_call(_CREATOR)


async def test_chat_holds_the_same_command_for_another_user():
    assert (await _chat_call(_OTHER))[COMMAND_FORCE_APPROVAL_KEY] is True


async def _terminal_decision(owner_id):
    handler = MagicMock(needs_approval=MagicMock(return_value=False))
    session = MagicMock(
        owner="alice", tenant_id=None, agent_id="a", agent_role="chat_agent", has_pending_approval=lambda: False
    )
    with (
        _env(CommandRisk.MODERATE, await _manager_with_rule()),
        patch("services.agent_terminal.ai_line_gate.owner_user_id", AsyncMock(return_value=owner_id)),
        patch.object(enforcement, "_report", AsyncMock()),
    ):
        return await decide_command(handler, session, _COMMAND, CommandRisk.MODERATE, force_approval=False)


async def test_the_terminal_runs_the_creators_rule_matched_command_unheld():
    assert await _terminal_decision(_CREATOR) == (True, None)


async def test_the_terminal_holds_it_for_another_user():
    assert await _terminal_decision(_OTHER) == (False, None)
